#include "internal.hpp"

#include <tuple>

namespace magic_geo::detail {

namespace {

constexpr int INITIAL_SURFACE_ORIGIN_DOMAIN_ID = 0;
constexpr int INITIAL_EXCHANGE_ORIGIN_DOMAIN_ID = 1;
constexpr int INITIAL_EXCHANGE_ORIGIN_KIND_ID = -1;
constexpr int INITIAL_EXCHANGE_ORIGIN_PLATE_ID = -1;
constexpr int SURFACE_RESERVOIR_ID = 0;
constexpr int UPPER_MANTLE_EXCHANGE_RESERVOIR_ID = 1;
constexpr int SUBDUCTED_SLAB_RESERVOIR_ID = 2;
constexpr int LEGACY_RULE_PROXY_COMPENSATION_MECHANISM_ID = 0;
constexpr int NO_FRAGMENT_ID = -1;
constexpr int NO_OWNER_ID = -1;
constexpr double DRY_ROCK_MASS_KG_PER_DENSITY_WEIGHTED_KM3 = 1.0e12;
constexpr double SURFACE_ENVELOPE_MAXIMUM_THICKNESS_KM = 76.0;
constexpr double SURFACE_ENVELOPE_MAXIMUM_DENSITY_G_CM3 = 3.08;

using Packet = CrustDryRockPacket;
using PacketTable = CrustDryRockPacketTable;
using TransferTable = CrustDryRockTransferTable;

auto packet_key(const Packet& packet) {
    return std::tuple{
        packet.origin_domain_id,
        packet.origin_kind_id,
        packet.origin_plate_id,
    };
}

bool packet_key_less(const Packet& left, const Packet& right) {
    return packet_key(left) < packet_key(right);
}

bool packet_key_equal(const Packet& left, const Packet& right) {
    return packet_key(left) == packet_key(right);
}

void validate_packet_key(const Packet& packet, int plate_count) {
    if (packet.origin_domain_id == INITIAL_SURFACE_ORIGIN_DOMAIN_ID) {
        if (
            packet.origin_kind_id < 0 || packet.origin_kind_id > 8 ||
            packet.origin_plate_id < 0 ||
            packet.origin_plate_id >= plate_count
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting surface-origin key is invalid"
            );
        }
        return;
    }
    if (packet.origin_domain_id == INITIAL_EXCHANGE_ORIGIN_DOMAIN_ID) {
        if (
            packet.origin_kind_id != INITIAL_EXCHANGE_ORIGIN_KIND_ID ||
            packet.origin_plate_id != INITIAL_EXCHANGE_ORIGIN_PLATE_ID
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting exchange-origin key is invalid"
            );
        }
        return;
    }
    throw std::runtime_error(
        "finite dry-rock accounting packet has an invalid origin domain"
    );
}

void validate_packet(const Packet& packet, int plate_count) {
    validate_packet_key(packet, plate_count);
    if (
        !std::isfinite(packet.dry_rock_mass_kg) ||
        packet.dry_rock_mass_kg <= 0.0
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting packet mass is nonfinite or nonpositive"
        );
    }
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

double checked_mass(double area_km2, double thickness_km, double density) {
    if (
        !std::isfinite(area_km2) || area_km2 <= 0.0 ||
        !std::isfinite(thickness_km) || thickness_km < 0.0 ||
        !std::isfinite(density) || density < 0.0
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting scalar state is invalid"
        );
    }
    const double mass = area_km2 * thickness_km * density *
        DRY_ROCK_MASS_KG_PER_DENSITY_WEIGHTED_KM3;
    if (!std::isfinite(mass) || mass < 0.0) {
        throw std::runtime_error(
            "finite dry-rock accounting scalar mass is invalid"
        );
    }
    return mass;
}

void normalize_packets(std::vector<Packet>& packets, int plate_count) {
    packets.erase(
        std::remove_if(
            packets.begin(), packets.end(),
            [](const Packet& packet) {
                if (
                    !std::isfinite(packet.dry_rock_mass_kg) ||
                    packet.dry_rock_mass_kg < 0.0
                ) {
                    throw std::runtime_error(
                        "finite dry-rock accounting produced invalid packet mass"
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
        validate_packet(packet, plate_count);
        if (!merged.empty() && packet_key_equal(merged.back(), packet)) {
            merged.back().dry_rock_mass_kg += packet.dry_rock_mass_kg;
            if (!std::isfinite(merged.back().dry_rock_mass_kg)) {
                throw std::runtime_error(
                    "finite dry-rock accounting packet coalescing overflowed"
                );
            }
        } else {
            merged.push_back(packet);
        }
    }
    packets = std::move(merged);
}

void validate_canonical_packets(
    const std::vector<Packet>& packets,
    int plate_count
) {
    for (std::size_t index = 0; index < packets.size(); ++index) {
        validate_packet(packets[index], plate_count);
        if (
            index > 0 &&
            !packet_key_less(packets[index - 1], packets[index])
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting packets are not canonical"
            );
        }
    }
}

bool merge_packet(
    std::vector<Packet>& packets,
    const Packet& addition,
    int plate_count,
    std::size_t maximum_owner_packet_count =
        std::numeric_limits<std::size_t>::max(),
    std::size_t live_packet_count = 0,
    bool enforce_live_limit_before_insert = false
) {
    validate_packet(addition, plate_count);
    const auto position = std::lower_bound(
        packets.begin(), packets.end(), addition, packet_key_less
    );
    if (position != packets.end() && packet_key_equal(*position, addition)) {
        position->dry_rock_mass_kg += addition.dry_rock_mass_kg;
        if (!std::isfinite(position->dry_rock_mass_kg)) {
            throw std::runtime_error(
                "finite dry-rock accounting packet merge overflowed"
            );
        }
        return false;
    } else {
        if (packets.size() >= maximum_owner_packet_count) {
            throw std::runtime_error(
                "finite dry-rock accounting surface-owner packet safety limit exceeded"
            );
        }
        if (
            enforce_live_limit_before_insert &&
            live_packet_count >= CRUST_DRY_ROCK_MAX_LIVE_RESERVOIR_PACKETS
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting live reservoir packet safety limit exceeded"
            );
        }
        packets.insert(position, addition);
        return true;
    }
}

void enforce_surface_owner_packet_limit(
    const std::vector<Packet>& packets
) {
    if (packets.size() > CRUST_DRY_ROCK_MAX_SURFACE_PACKETS_PER_OWNER) {
        throw std::runtime_error(
            "finite dry-rock accounting surface-owner packet safety limit exceeded"
        );
    }
}

std::size_t reservoir_packet_count(
    const std::vector<std::vector<Packet>>& surface,
    const std::vector<Packet>& mantle,
    const std::vector<std::vector<Packet>>& slab
) {
    std::size_t total = mantle.size();
    for (const auto& packets : surface) {
        if (packets.size() >
            std::numeric_limits<std::size_t>::max() - total) {
            throw std::runtime_error(
                "finite dry-rock accounting live packet count overflowed"
            );
        }
        total += packets.size();
    }
    for (const auto& packets : slab) {
        if (packets.size() >
            std::numeric_limits<std::size_t>::max() - total) {
            throw std::runtime_error(
                "finite dry-rock accounting live packet count overflowed"
            );
        }
        total += packets.size();
    }
    return total;
}

void enforce_live_packet_limit(std::size_t count) {
    if (count > CRUST_DRY_ROCK_MAX_LIVE_RESERVOIR_PACKETS) {
        throw std::runtime_error(
            "finite dry-rock accounting live reservoir packet safety limit exceeded"
        );
    }
}

long double packet_vector_mass(const std::vector<Packet>& packets) {
    long double total = 0.0L;
    for (const Packet& packet : packets) {
        total += packet.dry_rock_mass_kg;
    }
    return total;
}

PacketTable flatten_packets(
    const std::vector<std::vector<Packet>>& packets_by_owner,
    int plate_count
) {
    PacketTable table;
    table.owner_offsets.reserve(packets_by_owner.size() + 1);
    table.owner_offsets.push_back(0);
    for (const auto& packets : packets_by_owner) {
        validate_canonical_packets(packets, plate_count);
        for (const Packet& packet : packets) {
            table.origin_domain_ids.push_back(packet.origin_domain_id);
            table.origin_kind_ids.push_back(packet.origin_kind_id);
            table.origin_plate_ids.push_back(packet.origin_plate_id);
            table.dry_rock_mass_kg.push_back(packet.dry_rock_mass_kg);
        }
        table.owner_offsets.push_back(static_cast<int>(
            table.dry_rock_mass_kg.size()
        ));
    }
    return table;
}

PacketTable flatten_single_reservoir(
    const std::vector<Packet>& packets,
    int plate_count
) {
    return flatten_packets({packets}, plate_count);
}

bool packet_tables_equal(const PacketTable& left, const PacketTable& right) {
    return
        left.owner_offsets == right.owner_offsets &&
        left.origin_domain_ids == right.origin_domain_ids &&
        left.origin_kind_ids == right.origin_kind_ids &&
        left.origin_plate_ids == right.origin_plate_ids &&
        left.dry_rock_mass_kg == right.dry_rock_mass_kg;
}

long double packet_table_mass(const PacketTable& table) {
    long double total = 0.0L;
    for (double mass : table.dry_rock_mass_kg) {
        total += mass;
    }
    return total;
}

long double packet_table_owner_mass(
    const PacketTable& table,
    std::size_t owner_id
) {
    if (owner_id + 1 >= table.owner_offsets.size()) {
        throw std::runtime_error(
            "finite dry-rock accounting packet owner is out of range"
        );
    }
    long double total = 0.0L;
    for (
        int index = table.owner_offsets[owner_id];
        index < table.owner_offsets[owner_id + 1];
        ++index
    ) {
        total += table.dry_rock_mass_kg[static_cast<std::size_t>(index)];
    }
    return total;
}

long double shadow_table_owner_mass(
    const CrustMaterialShadowPacketTable& table,
    std::size_t owner_id
) {
    if (owner_id + 1 >= table.cell_offsets.size()) {
        throw std::runtime_error(
            "finite dry-rock accounting shadow owner is out of range"
        );
    }
    long double total = 0.0L;
    for (
        int index = table.cell_offsets[owner_id];
        index < table.cell_offsets[owner_id + 1];
        ++index
    ) {
        total += table.dry_rock_mass_kg[static_cast<std::size_t>(index)];
    }
    return total;
}

struct TransportEdge {
    int source_cell_id = 0;
    int destination_cell_id = 0;
    int original_edge_index = 0;
    double overlap_area_km2 = 0.0;
};

std::vector<std::vector<Packet>> transport_surface_packets(
    const CrustTransportPlan& plan,
    const std::vector<std::vector<Packet>>& opening,
    int plate_count,
    std::size_t& maximum_surface_packet_count_per_owner,
    std::size_t& transported_packet_count,
    std::size_t non_surface_packet_count
) {
    const std::size_t cell_count = opening.size();
    if (
        cell_count == 0 ||
        plan.destination_offsets.size() != cell_count + 1 ||
        plan.destination_offsets.front() != 0 ||
        plan.source_cell_ids.size() != plan.overlap_area_km2.size() ||
        plan.destination_offsets.back() !=
            static_cast<int>(plan.source_cell_ids.size())
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting received malformed transport"
        );
    }

    std::vector<TransportEdge> edges;
    edges.reserve(plan.source_cell_ids.size());
    for (std::size_t destination_id = 0;
         destination_id < cell_count;
         ++destination_id) {
        const int begin = plan.destination_offsets[destination_id];
        const int end = plan.destination_offsets[destination_id + 1];
        if (
            begin < 0 || end < begin ||
            end > static_cast<int>(plan.source_cell_ids.size())
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting transport offsets are invalid"
            );
        }
        for (int edge_index = begin; edge_index < end; ++edge_index) {
            const int source_id = plan.source_cell_ids[
                static_cast<std::size_t>(edge_index)
            ];
            const double area = plan.overlap_area_km2[
                static_cast<std::size_t>(edge_index)
            ];
            if (
                source_id < 0 ||
                source_id >= static_cast<int>(cell_count) ||
                !std::isfinite(area) || area <= 0.0
            ) {
                throw std::runtime_error(
                    "finite dry-rock accounting transport edge is invalid"
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

    std::vector<std::vector<Packet>> transported(cell_count);
    std::size_t edge_cursor = 0;
    for (std::size_t source_id = 0; source_id < cell_count; ++source_id) {
        const std::size_t source_edge_begin = edge_cursor;
        double overlap_sum = 0.0;
        while (
            edge_cursor < edges.size() &&
            edges[edge_cursor].source_cell_id == static_cast<int>(source_id)
        ) {
            overlap_sum += edges[edge_cursor].overlap_area_km2;
            edge_cursor++;
        }
        if (
            edge_cursor == source_edge_begin ||
            !std::isfinite(overlap_sum) || overlap_sum <= 0.0
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting source has no outgoing overlap"
            );
        }
        validate_canonical_packets(opening[source_id], plate_count);
        enforce_surface_owner_packet_limit(opening[source_id]);
        maximum_surface_packet_count_per_owner = std::max(
            maximum_surface_packet_count_per_owner,
            opening[source_id].size()
        );
        for (const Packet& packet : opening[source_id]) {
            double allocated = 0.0;
            for (std::size_t position = source_edge_begin;
                 position < edge_cursor;
                 ++position) {
                const bool last_edge = position + 1 == edge_cursor;
                const double edge_mass = last_edge
                    ? packet.dry_rock_mass_kg - allocated
                    : packet.dry_rock_mass_kg *
                        (edges[position].overlap_area_km2 / overlap_sum);
                if (!std::isfinite(edge_mass) || edge_mass < 0.0) {
                    throw std::runtime_error(
                        "finite dry-rock accounting edge allocation is invalid"
                    );
                }
                if (edge_mass > 0.0) {
                    Packet contribution = packet;
                    contribution.dry_rock_mass_kg = edge_mass;
                    auto& destination_packets = transported[
                        static_cast<std::size_t>(
                            edges[position].destination_cell_id
                        )
                    ];
                    const bool inserted = merge_packet(
                        destination_packets,
                        contribution,
                        plate_count,
                        CRUST_DRY_ROCK_MAX_SURFACE_PACKETS_PER_OWNER,
                        non_surface_packet_count + transported_packet_count,
                        true
                    );
                    if (inserted) {
                        transported_packet_count++;
                        enforce_surface_owner_packet_limit(
                            destination_packets
                        );
                        enforce_live_packet_limit(
                            non_surface_packet_count +
                                transported_packet_count
                        );
                        maximum_surface_packet_count_per_owner = std::max(
                            maximum_surface_packet_count_per_owner,
                            destination_packets.size()
                        );
                    }
                }
                allocated += edge_mass;
            }
            const long double residual =
                static_cast<long double>(allocated) -
                packet.dry_rock_mass_kg;
            if (
                std::abs(residual) > forward_error_bound(
                    std::abs(static_cast<long double>(allocated)) +
                        packet.dry_rock_mass_kg,
                    edge_cursor - source_edge_begin + 1
                )
            ) {
                throw std::runtime_error(
                    "finite dry-rock accounting source allocation did not close"
                );
            }
        }
    }
    if (edge_cursor != edges.size()) {
        throw std::runtime_error(
            "finite dry-rock accounting transport traversal did not close"
        );
    }
    for (const auto& packets : transported) {
        validate_canonical_packets(packets, plate_count);
    }
    return transported;
}

struct Withdrawal {
    std::vector<Packet> packets;
    double fulfilled_mass_kg = 0.0;
};

Withdrawal withdraw_packets(
    std::vector<Packet>& source,
    double requested_mass_kg,
    bool allow_bounded_surface_exhaustion,
    int plate_count,
    const char* insufficient_message
) {
    validate_canonical_packets(source, plate_count);
    if (!std::isfinite(requested_mass_kg) || requested_mass_kg <= 0.0) {
        throw std::runtime_error(
            "finite dry-rock accounting withdrawal request is invalid"
        );
    }
    const long double available_long = packet_vector_mass(source);
    if (available_long <= 0.0L) {
        throw std::runtime_error(insufficient_message);
    }
    const double available = checked_double(
        available_long,
        "finite dry-rock accounting available mass overflowed"
    );
    double fulfilled = requested_mass_kg;
    if (requested_mass_kg > available) {
        const long double excess =
            static_cast<long double>(requested_mass_kg) - available_long;
        const long double bound = forward_error_bound(
            available_long + requested_mass_kg,
            source.size() + 2
        );
        if (!allow_bounded_surface_exhaustion || excess > bound) {
            throw std::runtime_error(insufficient_message);
        }
        fulfilled = available;
    }

    if (fulfilled >= available) {
        Withdrawal result{source, available};
        source.clear();
        return result;
    }

    std::size_t correction_index = 0;
    for (std::size_t index = 1; index < source.size(); ++index) {
        if (
            source[index].dry_rock_mass_kg >
                source[correction_index].dry_rock_mass_kg
        ) {
            correction_index = index;
        }
    }
    std::vector<double> removals(source.size(), 0.0);
    double provisional = 0.0;
    for (std::size_t index = 0; index < source.size(); ++index) {
        removals[index] = fulfilled * source[index].dry_rock_mass_kg /
            available;
        provisional += removals[index];
    }
    removals[correction_index] += fulfilled - provisional;

    Withdrawal result;
    result.fulfilled_mass_kg = fulfilled;
    std::vector<Packet> retained;
    retained.reserve(source.size());
    for (std::size_t index = 0; index < source.size(); ++index) {
        const Packet& packet = source[index];
        const double removal = removals[index];
        if (
            !std::isfinite(removal) || removal < 0.0 ||
            removal > packet.dry_rock_mass_kg
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting proportional withdrawal failed"
            );
        }
        if (removal > 0.0) {
            Packet withdrawn = packet;
            withdrawn.dry_rock_mass_kg = removal;
            result.packets.push_back(withdrawn);
        }
        Packet remainder = packet;
        remainder.dry_rock_mass_kg -= removal;
        if (
            !std::isfinite(remainder.dry_rock_mass_kg) ||
            remainder.dry_rock_mass_kg < 0.0
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting withdrawal produced negative mass"
            );
        }
        if (remainder.dry_rock_mass_kg > 0.0) {
            retained.push_back(remainder);
        }
    }
    source = std::move(retained);
    normalize_packets(source, plate_count);
    normalize_packets(result.packets, plate_count);
    return result;
}

Withdrawal withdraw_exchange_packets(
    std::vector<Packet>& source,
    double requested_mass_kg,
    int plate_count
) {
    validate_canonical_packets(source, plate_count);
    if (!std::isfinite(requested_mass_kg) || requested_mass_kg <= 0.0) {
        throw std::runtime_error(
            "finite dry-rock accounting exchange withdrawal is invalid"
        );
    }
    const long double available = packet_vector_mass(source);
    if (static_cast<long double>(requested_mass_kg) > available) {
        throw std::runtime_error(
            "finite dry-rock accounting upper-mantle exchange reserve exhausted"
        );
    }

    Withdrawal result;
    result.fulfilled_mass_kg = requested_mass_kg;
    double remaining = requested_mass_kg;
    while (remaining > 0.0) {
        if (source.empty()) {
            throw std::runtime_error(
                "finite dry-rock accounting upper-mantle exchange reserve exhausted"
            );
        }
        const bool has_initial_exchange = std::any_of(
            source.begin(), source.end(),
            [](const Packet& packet) {
                return packet.origin_domain_id ==
                    INITIAL_EXCHANGE_ORIGIN_DOMAIN_ID;
            }
        );
        std::size_t selected = source.size();
        for (std::size_t index = 0; index < source.size(); ++index) {
            if (
                has_initial_exchange &&
                source[index].origin_domain_id !=
                    INITIAL_EXCHANGE_ORIGIN_DOMAIN_ID
            ) {
                continue;
            }
            if (
                selected == source.size() ||
                source[index].dry_rock_mass_kg >
                    source[selected].dry_rock_mass_kg
            ) {
                // Source packets are key-sorted, so strict greater-than
                // retains the lowest key when masses tie.
                selected = index;
            }
        }
        if (selected == source.size()) {
            throw std::runtime_error(
                "finite dry-rock accounting exchange selection failed"
            );
        }
        const double removal = std::min(
            remaining,
            source[selected].dry_rock_mass_kg
        );
        Packet withdrawn = source[selected];
        withdrawn.dry_rock_mass_kg = removal;
        result.packets.push_back(withdrawn);
        remaining -= removal;
        if (removal == source[selected].dry_rock_mass_kg) {
            source.erase(source.begin() + static_cast<std::ptrdiff_t>(selected));
        } else {
            source[selected].dry_rock_mass_kg -= removal;
            if (
                !std::isfinite(source[selected].dry_rock_mass_kg) ||
                source[selected].dry_rock_mass_kg <= 0.0
            ) {
                throw std::runtime_error(
                    "finite dry-rock accounting exchange depletion failed"
                );
            }
        }
    }
    normalize_packets(source, plate_count);
    normalize_packets(result.packets, plate_count);
    return result;
}

void append_transfer(
    TransferTable& table,
    int process_reason_id,
    int cell_id,
    int source_reservoir_id,
    int source_owner_id,
    int destination_reservoir_id,
    int destination_owner_id,
    const Packet& packet
) {
    if (table.dry_rock_mass_kg.size() >=
        CRUST_DRY_ROCK_MAX_PROXY_TRANSFERS_PER_STEP) {
        throw std::runtime_error(
            "finite dry-rock accounting per-step transfer safety limit exceeded"
        );
    }
    const int sequence_id = static_cast<int>(table.dry_rock_mass_kg.size());
    table.sequence_ids.push_back(sequence_id);
    table.mechanism_ids.push_back(
        LEGACY_RULE_PROXY_COMPENSATION_MECHANISM_ID
    );
    table.process_reason_ids.push_back(process_reason_id);
    table.cell_ids.push_back(cell_id);
    table.fragment_ids.push_back(NO_FRAGMENT_ID);
    table.source_reservoir_ids.push_back(source_reservoir_id);
    table.source_owner_ids.push_back(source_owner_id);
    table.destination_reservoir_ids.push_back(destination_reservoir_id);
    table.destination_owner_ids.push_back(destination_owner_id);
    table.origin_domain_ids.push_back(packet.origin_domain_id);
    table.origin_kind_ids.push_back(packet.origin_kind_id);
    table.origin_plate_ids.push_back(packet.origin_plate_id);
    table.physical_basis_resolved.push_back(0);
    table.dry_rock_mass_kg.push_back(packet.dry_rock_mass_kg);
}

using CellReasonMass =
    std::vector<std::array<double, CRUST_PROCESS_REASON_COUNT>>;

CellReasonMass adjustment_requests(
    const CrustMaterialShadowAdjustmentTable& table,
    std::size_t cell_count,
    const char* malformed_message
) {
    const std::size_t record_count = table.dry_rock_mass_kg.size();
    if (
        table.cell_offsets.size() != cell_count + 1 ||
        table.cell_offsets.front() != 0 ||
        table.cell_offsets.back() != static_cast<int>(record_count) ||
        table.process_reason_ids.size() != record_count ||
        table.origin_kind_ids.size() != record_count ||
        table.origin_plate_ids.size() != record_count ||
        table.origin_reason_ids.size() != record_count
    ) {
        throw std::runtime_error(malformed_message);
    }
    CellReasonMass requests(cell_count);
    for (std::size_t cell_id = 0; cell_id < cell_count; ++cell_id) {
        const int begin = table.cell_offsets[cell_id];
        const int end = table.cell_offsets[cell_id + 1];
        if (begin < 0 || end < begin || end > static_cast<int>(record_count)) {
            throw std::runtime_error(malformed_message);
        }
        for (int record = begin; record < end; ++record) {
            const std::size_t index = static_cast<std::size_t>(record);
            const int reason = table.process_reason_ids[index];
            const double mass = table.dry_rock_mass_kg[index];
            if (
                reason < 0 || reason >= CRUST_PROCESS_REASON_COUNT ||
                !std::isfinite(mass) || mass <= 0.0
            ) {
                throw std::runtime_error(malformed_message);
            }
            double& total = requests[cell_id][static_cast<std::size_t>(reason)];
            total += mass;
            if (!std::isfinite(total)) {
                throw std::runtime_error(malformed_message);
            }
        }
    }
    return requests;
}

using OriginKey = std::tuple<int, int, int>;

void add_origin_totals(
    std::map<OriginKey, long double>& totals,
    const std::vector<Packet>& packets
) {
    for (const Packet& packet : packets) {
        totals[packet_key(packet)] += packet.dry_rock_mass_kg;
    }
}

void add_origin_totals(
    std::map<OriginKey, long double>& totals,
    const std::vector<std::vector<Packet>>& packets_by_owner
) {
    for (const auto& packets : packets_by_owner) {
        add_origin_totals(totals, packets);
    }
}

std::map<OriginKey, long double> origin_totals(
    const std::vector<std::vector<Packet>>& surface,
    const std::vector<Packet>& mantle,
    const std::vector<std::vector<Packet>>& slab
) {
    std::map<OriginKey, long double> totals;
    add_origin_totals(totals, surface);
    add_origin_totals(totals, mantle);
    add_origin_totals(totals, slab);
    return totals;
}

long double transfer_mass_for_reservoir(
    const TransferTable& table,
    int reservoir_id,
    bool incoming
) {
    long double total = 0.0L;
    const auto& ids = incoming
        ? table.destination_reservoir_ids
        : table.source_reservoir_ids;
    for (std::size_t index = 0; index < ids.size(); ++index) {
        if (ids[index] == reservoir_id) {
            total += table.dry_rock_mass_kg[index];
        }
    }
    return total;
}

void validate_transfer_table(
    const TransferTable& table,
    int cell_count,
    int plate_count
) {
    const std::size_t count = table.dry_rock_mass_kg.size();
    if (
        table.sequence_ids.size() != count ||
        table.mechanism_ids.size() != count ||
        table.process_reason_ids.size() != count ||
        table.cell_ids.size() != count ||
        table.fragment_ids.size() != count ||
        table.source_reservoir_ids.size() != count ||
        table.source_owner_ids.size() != count ||
        table.destination_reservoir_ids.size() != count ||
        table.destination_owner_ids.size() != count ||
        table.origin_domain_ids.size() != count ||
        table.origin_kind_ids.size() != count ||
        table.origin_plate_ids.size() != count ||
        table.physical_basis_resolved.size() != count
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting transfer table is malformed"
        );
    }
    for (std::size_t index = 0; index < count; ++index) {
        const int cell_id = table.cell_ids[index];
        const int source_reservoir = table.source_reservoir_ids[index];
        const int destination_reservoir =
            table.destination_reservoir_ids[index];
        const int source_owner = table.source_owner_ids[index];
        const int destination_owner = table.destination_owner_ids[index];
        const bool surface_to_mantle =
            source_reservoir == SURFACE_RESERVOIR_ID &&
            destination_reservoir == UPPER_MANTLE_EXCHANGE_RESERVOIR_ID &&
            source_owner == cell_id && destination_owner == NO_OWNER_ID;
        const bool mantle_to_surface =
            source_reservoir == UPPER_MANTLE_EXCHANGE_RESERVOIR_ID &&
            destination_reservoir == SURFACE_RESERVOIR_ID &&
            source_owner == NO_OWNER_ID && destination_owner == cell_id;
        validate_packet_key(Packet{
            table.origin_domain_ids[index],
            table.origin_kind_ids[index],
            table.origin_plate_ids[index],
            table.dry_rock_mass_kg[index],
        }, plate_count);
        if (
            table.sequence_ids[index] != static_cast<int>(index) ||
            table.mechanism_ids[index] !=
                LEGACY_RULE_PROXY_COMPENSATION_MECHANISM_ID ||
            table.process_reason_ids[index] < 0 ||
            table.process_reason_ids[index] >= CRUST_PROCESS_REASON_COUNT ||
            cell_id < 0 || cell_id >= cell_count ||
            table.fragment_ids[index] != NO_FRAGMENT_ID ||
            table.physical_basis_resolved[index] != 0 ||
            !std::isfinite(table.dry_rock_mass_kg[index]) ||
            table.dry_rock_mass_kg[index] <= 0.0 ||
            (!surface_to_mantle && !mantle_to_surface) ||
            source_reservoir == SUBDUCTED_SLAB_RESERVOIR_ID ||
            destination_reservoir == SUBDUCTED_SLAB_RESERVOIR_ID
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting transfer record is invalid"
            );
        }
    }
}

void populate_step_counts(CrustDryRockAccountingStep& step) {
    step.opening_surface_packet_count = static_cast<int>(
        step.opening_surface_packets.dry_rock_mass_kg.size()
    );
    step.transported_surface_packet_count = static_cast<int>(
        step.transported_surface_packets.dry_rock_mass_kg.size()
    );
    step.closing_surface_packet_count = static_cast<int>(
        step.closing_surface_packets.dry_rock_mass_kg.size()
    );
    step.opening_upper_mantle_packet_count = static_cast<int>(
        step.opening_upper_mantle_packets.dry_rock_mass_kg.size()
    );
    step.closing_upper_mantle_packet_count = static_cast<int>(
        step.closing_upper_mantle_packets.dry_rock_mass_kg.size()
    );
    step.opening_subducted_slab_packet_count = static_cast<int>(
        step.opening_subducted_slab_packets.dry_rock_mass_kg.size()
    );
    step.closing_subducted_slab_packet_count = static_cast<int>(
        step.closing_subducted_slab_packets.dry_rock_mass_kg.size()
    );
    step.proxy_compensation_transfer_count = static_cast<int>(
        step.proxy_compensation_transfers.dry_rock_mass_kg.size()
    );
}

}  // namespace

void initialize_crust_dry_rock_accounting(
    const std::vector<Cell>& cells,
    int plate_count,
    int plate_motion_history_id,
    int crust_material_shadow_history_id,
    int erosion_iteration,
    const std::string& stage,
    CrustDryRockAccountingState& state
) {
    if (
        cells.empty() || plate_count <= 0 ||
        plate_motion_history_id < 0 ||
        crust_material_shadow_history_id < 0 || stage.empty() ||
        !state.surface_packets_by_cell.empty() ||
        !state.upper_mantle_packets.empty() ||
        !state.subducted_slab_packets_by_plate.empty() ||
        !state.history.empty()
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting initialization state is malformed"
        );
    }

    state.surface_packets_by_cell.resize(cells.size());
    long double surface_mass = 0.0L;
    long double total_area = 0.0L;
    for (std::size_t cell_id = 0; cell_id < cells.size(); ++cell_id) {
        const Cell& cell = cells[cell_id];
        if (
            cell.crust_type < 0 || cell.crust_type > 8 ||
            cell.plate_id < 0 || cell.plate_id >= plate_count
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting initial surface key is invalid"
            );
        }
        const double mass = checked_mass(
            cell.area_km2,
            cell.crust_thickness_km,
            cell.crust_density
        );
        state.surface_packets_by_cell[cell_id].push_back(Packet{
            INITIAL_SURFACE_ORIGIN_DOMAIN_ID,
            cell.crust_type,
            cell.plate_id,
            mass,
        });
        surface_mass += mass;
        total_area += cell.area_km2;
    }
    const std::size_t initial_surface_packet_count = cells.size();
    enforce_live_packet_limit(initial_surface_packet_count);
    const long double envelope_capacity = total_area *
        SURFACE_ENVELOPE_MAXIMUM_THICKNESS_KM *
        SURFACE_ENVELOPE_MAXIMUM_DENSITY_G_CM3 *
        DRY_ROCK_MASS_KG_PER_DENSITY_WEIGHTED_KM3;
    if (
        !std::isfinite(envelope_capacity) ||
        envelope_capacity <= 0.0L || surface_mass > envelope_capacity
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting surface envelope cannot contain initial crust"
        );
    }
    const double mantle_mass = checked_double(
        envelope_capacity - surface_mass,
        "finite dry-rock accounting initial exchange reserve overflowed"
    );
    if (mantle_mass > 0.0) {
        state.upper_mantle_packets.push_back(Packet{
            INITIAL_EXCHANGE_ORIGIN_DOMAIN_ID,
            INITIAL_EXCHANGE_ORIGIN_KIND_ID,
            INITIAL_EXCHANGE_ORIGIN_PLATE_ID,
            mantle_mass,
        });
    }
    enforce_live_packet_limit(
        initial_surface_packet_count + state.upper_mantle_packets.size()
    );
    state.subducted_slab_packets_by_plate.resize(
        static_cast<std::size_t>(plate_count)
    );
    state.surface_state_envelope_capacity_kg = checked_double(
        envelope_capacity,
        "finite dry-rock accounting surface envelope overflowed"
    );
    state.total_control_volume_area_km2 = checked_double(
        total_area,
        "finite dry-rock accounting total area overflowed"
    );

    CrustDryRockAccountingStep step;
    step.id = 0;
    step.plate_motion_history_id = plate_motion_history_id;
    step.crust_material_shadow_history_id =
        crust_material_shadow_history_id;
    step.erosion_iteration = erosion_iteration;
    step.stage = stage;
    step.cell_count = static_cast<int>(cells.size());
    step.plate_count = plate_count;
    step.surface_state_envelope_capacity_kg =
        state.surface_state_envelope_capacity_kg;
    step.total_control_volume_area_km2 = state.total_control_volume_area_km2;
    step.opening_surface_packets = flatten_packets(
        state.surface_packets_by_cell, plate_count
    );
    step.transported_surface_packets = step.opening_surface_packets;
    step.closing_surface_packets = step.opening_surface_packets;
    step.opening_upper_mantle_packets = flatten_single_reservoir(
        state.upper_mantle_packets, plate_count
    );
    step.closing_upper_mantle_packets = step.opening_upper_mantle_packets;
    step.opening_subducted_slab_packets = flatten_packets(
        state.subducted_slab_packets_by_plate, plate_count
    );
    step.closing_subducted_slab_packets =
        step.opening_subducted_slab_packets;
    step.opening_surface_mass_kg = checked_double(
        surface_mass,
        "finite dry-rock accounting initial surface mass overflowed"
    );
    step.transported_surface_mass_kg = step.opening_surface_mass_kg;
    step.closing_surface_mass_kg = step.opening_surface_mass_kg;
    step.opening_upper_mantle_mass_kg = mantle_mass;
    step.closing_upper_mantle_mass_kg = mantle_mass;
    step.opening_global_mass_kg = checked_double(
        surface_mass + mantle_mass,
        "finite dry-rock accounting initial global mass overflowed"
    );
    step.closing_global_mass_kg = step.opening_global_mass_kg;
    step.closing_scalar_mass_kg = step.closing_surface_mass_kg;
    step.capacity_initialization_residual_kg = checked_double(
        static_cast<long double>(step.opening_global_mass_kg) -
            envelope_capacity,
        "finite dry-rock accounting capacity residual overflowed"
    );
    const long double capacity_bound = forward_error_bound(
        std::abs(surface_mass) + std::abs(static_cast<long double>(mantle_mass)) +
            std::abs(envelope_capacity),
        cells.size() + 4
    );
    if (std::abs(static_cast<long double>(
            step.capacity_initialization_residual_kg
        )) > capacity_bound) {
        throw std::runtime_error(
            "finite dry-rock accounting initial capacity did not close"
        );
    }
    populate_step_counts(step);
    step.maximum_surface_packet_count_per_owner = 1;
    step.maximum_live_reservoir_packet_count = static_cast<int>(
        initial_surface_packet_count + state.upper_mantle_packets.size()
    );
    state.history.push_back(std::move(step));
}

void advance_crust_dry_rock_accounting_step(
    const std::vector<Cell>& cells,
    int plate_count,
    const CrustTransportPlan& transport_plan,
    const CrustMaterialShadowStep& shadow_step,
    CrustDryRockAccountingState& state
) {
    const std::size_t cell_count = cells.size();
    if (
        cell_count == 0 || plate_count <= 0 ||
        state.surface_packets_by_cell.size() != cell_count ||
        state.subducted_slab_packets_by_plate.size() !=
            static_cast<std::size_t>(plate_count) ||
        state.history.empty() ||
        shadow_step.id != static_cast<int>(state.history.size()) ||
        shadow_step.plate_motion_history_id != shadow_step.id ||
        shadow_step.cell_count != static_cast<int>(cell_count) ||
        shadow_step.stage.empty()
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting step linkage is malformed"
        );
    }

    // Work on copies so depletion or any failed invariant leaves the
    // externally visible accounting state unchanged.
    auto surface = state.surface_packets_by_cell;
    auto mantle = state.upper_mantle_packets;
    auto slab = state.subducted_slab_packets_by_plate;
    std::size_t maximum_surface_packet_count_per_owner = 0;
    for (const auto& packets : surface) {
        enforce_surface_owner_packet_limit(packets);
        maximum_surface_packet_count_per_owner = std::max(
            maximum_surface_packet_count_per_owner,
            packets.size()
        );
    }
    std::size_t live_packet_count = reservoir_packet_count(
        surface, mantle, slab
    );
    enforce_live_packet_limit(live_packet_count);
    std::size_t maximum_live_reservoir_packet_count = live_packet_count;
    const auto opening_origin_totals = origin_totals(surface, mantle, slab);

    CrustDryRockAccountingStep step;
    step.id = shadow_step.id;
    step.plate_motion_history_id = shadow_step.plate_motion_history_id;
    step.crust_material_shadow_history_id = shadow_step.id;
    step.erosion_iteration = shadow_step.erosion_iteration;
    step.stage = shadow_step.stage;
    step.cell_count = static_cast<int>(cell_count);
    step.plate_count = plate_count;
    step.surface_state_envelope_capacity_kg =
        state.surface_state_envelope_capacity_kg;
    step.total_control_volume_area_km2 = state.total_control_volume_area_km2;
    step.opening_surface_packets = flatten_packets(surface, plate_count);
    step.opening_upper_mantle_packets = flatten_single_reservoir(
        mantle, plate_count
    );
    step.opening_subducted_slab_packets = flatten_packets(slab, plate_count);
    const CrustDryRockAccountingStep& previous = state.history.back();
    if (
        !packet_tables_equal(
            step.opening_surface_packets,
            previous.closing_surface_packets
        ) ||
        !packet_tables_equal(
            step.opening_upper_mantle_packets,
            previous.closing_upper_mantle_packets
        ) ||
        !packet_tables_equal(
            step.opening_subducted_slab_packets,
            previous.closing_subducted_slab_packets
        )
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting opening state does not link exactly"
        );
    }

    std::size_t transported_packet_count = 0;
    std::size_t non_surface_packet_count = mantle.size();
    for (const auto& packets : slab) {
        non_surface_packet_count += packets.size();
    }
    surface = transport_surface_packets(
        transport_plan,
        surface,
        plate_count,
        maximum_surface_packet_count_per_owner,
        transported_packet_count,
        non_surface_packet_count
    );
    live_packet_count = transported_packet_count + mantle.size();
    for (const auto& packets : slab) {
        if (packets.size() >
            std::numeric_limits<std::size_t>::max() - live_packet_count) {
            throw std::runtime_error(
                "finite dry-rock accounting live packet count overflowed"
            );
        }
        live_packet_count += packets.size();
    }
    enforce_live_packet_limit(live_packet_count);
    maximum_live_reservoir_packet_count = std::max(
        maximum_live_reservoir_packet_count,
        live_packet_count
    );
    step.transported_surface_packets = flatten_packets(surface, plate_count);
    const long double opening_surface_mass = packet_table_mass(
        step.opening_surface_packets
    );
    const long double transported_surface_mass = packet_table_mass(
        step.transported_surface_packets
    );
    const long double transport_residual =
        transported_surface_mass - opening_surface_mass;
    const long double transport_bound = forward_error_bound(
        std::abs(opening_surface_mass) +
            std::abs(transported_surface_mass),
        step.opening_surface_packets.dry_rock_mass_kg.size() +
            step.transported_surface_packets.dry_rock_mass_kg.size() +
            transport_plan.overlap_area_km2.size() + 2
    );
    if (std::abs(transport_residual) > transport_bound) {
        throw std::runtime_error(
            "finite dry-rock accounting transport did not conserve surface mass"
        );
    }
    if (
        shadow_step.transported_packets.cell_offsets.size() != cell_count + 1 ||
        shadow_step.closing_packets.cell_offsets.size() != cell_count + 1
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting received malformed shadow snapshots"
        );
    }
    for (std::size_t cell_id = 0; cell_id < cell_count; ++cell_id) {
        const long double accounting_mass = packet_table_owner_mass(
            step.transported_surface_packets, cell_id
        );
        const long double shadow_mass = shadow_table_owner_mass(
            shadow_step.transported_packets, cell_id
        );
        const long double bound = forward_error_bound(
            std::abs(accounting_mass) + std::abs(shadow_mass),
            static_cast<std::size_t>(
                step.transported_surface_packets.owner_offsets[cell_id + 1] -
                step.transported_surface_packets.owner_offsets[cell_id] +
                shadow_step.transported_packets.cell_offsets[cell_id + 1] -
                shadow_step.transported_packets.cell_offsets[cell_id] + 4
            )
        );
        if (std::abs(accounting_mass - shadow_mass) > bound) {
            throw std::runtime_error(
                "finite dry-rock accounting transport diverged from Phase-S"
            );
        }
    }

    const CellReasonMass source_requests = adjustment_requests(
        shadow_step.unresolved_source_adjustments,
        cell_count,
        "finite dry-rock accounting source requests are malformed"
    );
    const CellReasonMass sink_requests = adjustment_requests(
        shadow_step.unresolved_sink_adjustments,
        cell_count,
        "finite dry-rock accounting sink requests are malformed"
    );

    for (int reason = 0; reason < CRUST_PROCESS_REASON_COUNT; ++reason) {
        long double requested_source = 0.0L;
        long double requested_sink = 0.0L;
        for (std::size_t cell_id = 0; cell_id < cell_count; ++cell_id) {
            const double source = source_requests[cell_id][
                static_cast<std::size_t>(reason)
            ];
            const double sink = sink_requests[cell_id][
                static_cast<std::size_t>(reason)
            ];
            if (source > 0.0 && sink > 0.0) {
                throw std::runtime_error(
                    "finite dry-rock accounting cell/reason has both signs"
                );
            }
            requested_source += source;
            requested_sink += sink;
        }
        if (
            (reason == CRUST_PROCESS_QUIET_OCEANIC_AGING ||
             reason == CRUST_PROCESS_OCEANIC_RIDGE_REJUVENATION ||
             reason == CRUST_PROCESS_AGE_BOUND_ENFORCEMENT) &&
            (requested_source != 0.0L || requested_sink != 0.0L)
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting age-only reason changed mass"
            );
        }
        const std::size_t reason_index = static_cast<std::size_t>(reason);
        const long double shadow_source_reason =
            shadow_step.unresolved_source_mass_kg_by_reason[reason_index];
        const long double shadow_sink_reason =
            shadow_step.unresolved_sink_mass_kg_by_reason[reason_index];
        const long double reason_request_bound = forward_error_bound(
            requested_source + requested_sink +
                std::abs(shadow_source_reason) +
                std::abs(shadow_sink_reason),
            cell_count + 8
        );
        if (
            std::abs(requested_source - shadow_source_reason) >
                reason_request_bound ||
            std::abs(requested_sink - shadow_sink_reason) >
                reason_request_bound
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting requests do not match Phase-S reason totals"
            );
        }
        step.requested_surface_source_mass_kg_by_reason[
            static_cast<std::size_t>(reason)
        ] = checked_double(
            requested_source,
            "finite dry-rock accounting requested source mass overflowed"
        );
        step.requested_surface_sink_mass_kg_by_reason[
            static_cast<std::size_t>(reason)
        ] = checked_double(
            requested_sink,
            "finite dry-rock accounting requested sink mass overflowed"
        );

        // Canonical reason transaction: all surface sinks are committed in
        // ascending cell/key order before any source withdrawal for the same
        // reason.  The state copies make the whole step externally atomic.
        long double fulfilled_sink = 0.0L;
        for (std::size_t cell_id = 0; cell_id < cell_count; ++cell_id) {
            const double request = sink_requests[cell_id][
                static_cast<std::size_t>(reason)
            ];
            if (request == 0.0) {
                continue;
            }
            const std::size_t surface_packet_count_before =
                surface[cell_id].size();
            Withdrawal withdrawal = withdraw_packets(
                surface[cell_id],
                request,
                true,
                plate_count,
                "finite dry-rock accounting surface sink exceeds available mass"
            );
            const std::size_t surface_packet_count_after =
                surface[cell_id].size();
            if (surface_packet_count_after > surface_packet_count_before) {
                throw std::runtime_error(
                    "finite dry-rock accounting surface withdrawal grew its source"
                );
            }
            live_packet_count -=
                surface_packet_count_before - surface_packet_count_after;
            fulfilled_sink += withdrawal.fulfilled_mass_kg;
            for (const Packet& packet : withdrawal.packets) {
                const bool inserted = merge_packet(
                    mantle,
                    packet,
                    plate_count,
                    std::numeric_limits<std::size_t>::max(),
                    live_packet_count,
                    true
                );
                if (inserted) {
                    live_packet_count++;
                    enforce_live_packet_limit(live_packet_count);
                    maximum_live_reservoir_packet_count = std::max(
                        maximum_live_reservoir_packet_count,
                        live_packet_count
                    );
                }
                append_transfer(
                    step.proxy_compensation_transfers,
                    reason,
                    static_cast<int>(cell_id),
                    SURFACE_RESERVOIR_ID,
                    static_cast<int>(cell_id),
                    UPPER_MANTLE_EXCHANGE_RESERVOIR_ID,
                    NO_OWNER_ID,
                    packet
                );
            }
        }

        const long double available_after_sinks = packet_vector_mass(mantle);
        if (requested_source > available_after_sinks) {
            throw std::runtime_error(
                "finite dry-rock accounting upper-mantle exchange reserve exhausted"
            );
        }
        long double fulfilled_source = 0.0L;
        for (std::size_t cell_id = 0; cell_id < cell_count; ++cell_id) {
            const double request = source_requests[cell_id][
                static_cast<std::size_t>(reason)
            ];
            if (request == 0.0) {
                continue;
            }
            const std::size_t mantle_packet_count_before = mantle.size();
            Withdrawal withdrawal = withdraw_exchange_packets(
                mantle,
                request,
                plate_count
            );
            const std::size_t mantle_packet_count_after = mantle.size();
            if (mantle_packet_count_after > mantle_packet_count_before) {
                throw std::runtime_error(
                    "finite dry-rock accounting mantle withdrawal grew its source"
                );
            }
            live_packet_count -=
                mantle_packet_count_before - mantle_packet_count_after;
            fulfilled_source += withdrawal.fulfilled_mass_kg;
            for (const Packet& packet : withdrawal.packets) {
                const bool inserted = merge_packet(
                    surface[cell_id],
                    packet,
                    plate_count,
                    CRUST_DRY_ROCK_MAX_SURFACE_PACKETS_PER_OWNER,
                    live_packet_count,
                    true
                );
                enforce_surface_owner_packet_limit(surface[cell_id]);
                maximum_surface_packet_count_per_owner = std::max(
                    maximum_surface_packet_count_per_owner,
                    surface[cell_id].size()
                );
                if (inserted) {
                    live_packet_count++;
                    enforce_live_packet_limit(live_packet_count);
                    maximum_live_reservoir_packet_count = std::max(
                        maximum_live_reservoir_packet_count,
                        live_packet_count
                    );
                }
                append_transfer(
                    step.proxy_compensation_transfers,
                    reason,
                    static_cast<int>(cell_id),
                    UPPER_MANTLE_EXCHANGE_RESERVOIR_ID,
                    NO_OWNER_ID,
                    SURFACE_RESERVOIR_ID,
                    static_cast<int>(cell_id),
                    packet
                );
            }
        }
        step.fulfilled_surface_source_mass_kg_by_reason[
            static_cast<std::size_t>(reason)
        ] = checked_double(
            fulfilled_source,
            "finite dry-rock accounting fulfilled source mass overflowed"
        );
        step.fulfilled_surface_sink_mass_kg_by_reason[
            static_cast<std::size_t>(reason)
        ] = checked_double(
            fulfilled_sink,
            "finite dry-rock accounting fulfilled sink mass overflowed"
        );
    }

    validate_transfer_table(
        step.proxy_compensation_transfers,
        static_cast<int>(cell_count),
        plate_count
    );
    std::array<long double, CRUST_PROCESS_REASON_COUNT>
        transfer_source_mass_by_reason{};
    std::array<long double, CRUST_PROCESS_REASON_COUNT>
        transfer_sink_mass_by_reason{};
    for (std::size_t transfer_index = 0;
         transfer_index <
            step.proxy_compensation_transfers.dry_rock_mass_kg.size();
         ++transfer_index) {
        const std::size_t reason_index = static_cast<std::size_t>(
            step.proxy_compensation_transfers.process_reason_ids[
                transfer_index
            ]
        );
        const double mass =
            step.proxy_compensation_transfers.dry_rock_mass_kg[
                transfer_index
            ];
        if (
            step.proxy_compensation_transfers.source_reservoir_ids[
                transfer_index
            ] == UPPER_MANTLE_EXCHANGE_RESERVOIR_ID
        ) {
            transfer_source_mass_by_reason[reason_index] += mass;
        } else {
            transfer_sink_mass_by_reason[reason_index] += mass;
        }
    }
    for (int reason = 0; reason < CRUST_PROCESS_REASON_COUNT; ++reason) {
        const std::size_t reason_index = static_cast<std::size_t>(reason);
        const long double fulfilled_source =
            step.fulfilled_surface_source_mass_kg_by_reason[reason_index];
        const long double fulfilled_sink =
            step.fulfilled_surface_sink_mass_kg_by_reason[reason_index];
        const long double transfer_bound = forward_error_bound(
            std::abs(fulfilled_source) + std::abs(fulfilled_sink) +
                transfer_source_mass_by_reason[reason_index] +
                transfer_sink_mass_by_reason[reason_index],
            step.proxy_compensation_transfers.dry_rock_mass_kg.size() + 8
        );
        if (
            std::abs(
                transfer_source_mass_by_reason[reason_index] -
                fulfilled_source
            ) > transfer_bound ||
            std::abs(
                transfer_sink_mass_by_reason[reason_index] -
                fulfilled_sink
            ) > transfer_bound
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting transfer reasons do not reconcile"
            );
        }
    }
    for (auto& packets : surface) {
        normalize_packets(packets, plate_count);
    }
    normalize_packets(mantle, plate_count);
    for (auto& packets : slab) {
        normalize_packets(packets, plate_count);
    }
    const std::size_t closing_live_packet_count = reservoir_packet_count(
        surface, mantle, slab
    );
    enforce_live_packet_limit(closing_live_packet_count);
    if (closing_live_packet_count != live_packet_count) {
        throw std::runtime_error(
            "finite dry-rock accounting incremental live packet count diverged"
        );
    }
    step.closing_surface_packets = flatten_packets(surface, plate_count);
    step.closing_upper_mantle_packets = flatten_single_reservoir(
        mantle, plate_count
    );
    step.closing_subducted_slab_packets = flatten_packets(slab, plate_count);

    const long double opening_mantle_mass = packet_table_mass(
        step.opening_upper_mantle_packets
    );
    const long double closing_surface_mass = packet_table_mass(
        step.closing_surface_packets
    );
    const long double closing_mantle_mass = packet_table_mass(
        step.closing_upper_mantle_packets
    );
    const long double opening_slab_mass = packet_table_mass(
        step.opening_subducted_slab_packets
    );
    const long double closing_slab_mass = packet_table_mass(
        step.closing_subducted_slab_packets
    );
    const long double opening_global =
        opening_surface_mass + opening_mantle_mass + opening_slab_mass;
    const long double closing_global =
        closing_surface_mass + closing_mantle_mass + closing_slab_mass;

    step.opening_surface_mass_kg = checked_double(
        opening_surface_mass,
        "finite dry-rock accounting opening surface mass overflowed"
    );
    step.transported_surface_mass_kg = checked_double(
        transported_surface_mass,
        "finite dry-rock accounting transported surface mass overflowed"
    );
    step.closing_surface_mass_kg = checked_double(
        closing_surface_mass,
        "finite dry-rock accounting closing surface mass overflowed"
    );
    step.opening_upper_mantle_mass_kg = checked_double(
        opening_mantle_mass,
        "finite dry-rock accounting opening mantle mass overflowed"
    );
    step.closing_upper_mantle_mass_kg = checked_double(
        closing_mantle_mass,
        "finite dry-rock accounting closing mantle mass overflowed"
    );
    step.opening_subducted_slab_mass_kg = checked_double(
        opening_slab_mass,
        "finite dry-rock accounting opening slab mass overflowed"
    );
    step.closing_subducted_slab_mass_kg = checked_double(
        closing_slab_mass,
        "finite dry-rock accounting closing slab mass overflowed"
    );
    step.opening_global_mass_kg = checked_double(
        opening_global,
        "finite dry-rock accounting opening global mass overflowed"
    );
    step.closing_global_mass_kg = checked_double(
        closing_global,
        "finite dry-rock accounting closing global mass overflowed"
    );
    step.source_to_transport_residual_kg = checked_double(
        transport_residual,
        "finite dry-rock accounting transport residual overflowed"
    );
    step.global_accounting_residual_kg = checked_double(
        closing_global - opening_global,
        "finite dry-rock accounting global residual overflowed"
    );
    step.capacity_initialization_residual_kg = checked_double(
        opening_global - state.surface_state_envelope_capacity_kg,
        "finite dry-rock accounting capacity residual overflowed"
    );

    long double scalar_mass = 0.0L;
    long double maximum_cell_scalar_residual = 0.0L;
    for (std::size_t cell_id = 0; cell_id < cell_count; ++cell_id) {
        const long double scalar_cell_mass = checked_mass(
            cells[cell_id].area_km2,
            cells[cell_id].crust_thickness_km,
            cells[cell_id].crust_density
        );
        const long double accounting_cell_mass = packet_table_owner_mass(
            step.closing_surface_packets, cell_id
        );
        const long double shadow_cell_mass = shadow_table_owner_mass(
            shadow_step.closing_packets, cell_id
        );
        scalar_mass += scalar_cell_mass;
        maximum_cell_scalar_residual = std::max(
            maximum_cell_scalar_residual,
            std::abs(accounting_cell_mass - scalar_cell_mass)
        );
        const long double bound = forward_error_bound(
            std::abs(accounting_cell_mass) +
                std::abs(shadow_cell_mass) +
                std::abs(scalar_cell_mass),
            static_cast<std::size_t>(
                step.closing_surface_packets.owner_offsets[cell_id + 1] -
                step.closing_surface_packets.owner_offsets[cell_id] +
                shadow_step.closing_packets.cell_offsets[cell_id + 1] -
                shadow_step.closing_packets.cell_offsets[cell_id] + 6
            )
        );
        const long double shadow_scalar_residual =
            std::abs(shadow_cell_mass - scalar_cell_mass);
        if (
            std::abs(accounting_cell_mass - shadow_cell_mass) > bound ||
            std::abs(accounting_cell_mass - scalar_cell_mass) >
                bound + shadow_scalar_residual
        ) {
            throw std::runtime_error(
                "finite dry-rock accounting closing surface diverged from scalar state"
            );
        }
    }
    step.closing_scalar_mass_kg = checked_double(
        scalar_mass,
        "finite dry-rock accounting scalar mass overflowed"
    );
    step.closing_scalar_mass_residual_kg = checked_double(
        closing_surface_mass - scalar_mass,
        "finite dry-rock accounting scalar residual overflowed"
    );
    step.maximum_absolute_cell_closing_scalar_mass_residual_kg = checked_double(
        maximum_cell_scalar_residual,
        "finite dry-rock accounting maximum cell residual overflowed"
    );

    long double requested_source_total = 0.0L;
    long double fulfilled_source_total = 0.0L;
    long double requested_sink_total = 0.0L;
    long double fulfilled_sink_total = 0.0L;
    for (int reason = 0; reason < CRUST_PROCESS_REASON_COUNT; ++reason) {
        requested_source_total +=
            step.requested_surface_source_mass_kg_by_reason[
                static_cast<std::size_t>(reason)
            ];
        fulfilled_source_total +=
            step.fulfilled_surface_source_mass_kg_by_reason[
                static_cast<std::size_t>(reason)
            ];
        requested_sink_total +=
            step.requested_surface_sink_mass_kg_by_reason[
                static_cast<std::size_t>(reason)
            ];
        fulfilled_sink_total +=
            step.fulfilled_surface_sink_mass_kg_by_reason[
                static_cast<std::size_t>(reason)
            ];
    }
    step.requested_minus_fulfilled_source_mass_kg = checked_double(
        requested_source_total - fulfilled_source_total,
        "finite dry-rock accounting source fulfillment residual overflowed"
    );
    step.requested_minus_fulfilled_sink_mass_kg = checked_double(
        requested_sink_total - fulfilled_sink_total,
        "finite dry-rock accounting sink fulfillment residual overflowed"
    );

    const auto closing_origin_totals = origin_totals(surface, mantle, slab);
    std::map<OriginKey, long double> all_origins = opening_origin_totals;
    for (const auto& [key, mass] : closing_origin_totals) {
        (void)mass;
        all_origins.try_emplace(key, 0.0L);
    }
    long double maximum_origin_residual = 0.0L;
    for (const auto& [key, ignored] : all_origins) {
        (void)ignored;
        const auto opening_position = opening_origin_totals.find(key);
        const auto closing_position = closing_origin_totals.find(key);
        const long double opening_value = opening_position ==
                opening_origin_totals.end()
            ? 0.0L
            : opening_position->second;
        const long double closing_value = closing_position ==
                closing_origin_totals.end()
            ? 0.0L
            : closing_position->second;
        maximum_origin_residual = std::max(
            maximum_origin_residual,
            std::abs(closing_value - opening_value)
        );
    }
    step.maximum_absolute_origin_closure_residual_kg = checked_double(
        maximum_origin_residual,
        "finite dry-rock accounting origin residual overflowed"
    );

    long double maximum_reservoir_residual = 0.0L;
    const std::array<long double, 3> reservoir_opening{
        transported_surface_mass,
        opening_mantle_mass,
        opening_slab_mass,
    };
    const std::array<long double, 3> reservoir_closing{
        closing_surface_mass,
        closing_mantle_mass,
        closing_slab_mass,
    };
    for (int reservoir = 0; reservoir < 3; ++reservoir) {
        const long double incoming = transfer_mass_for_reservoir(
            step.proxy_compensation_transfers, reservoir, true
        );
        const long double outgoing = transfer_mass_for_reservoir(
            step.proxy_compensation_transfers, reservoir, false
        );
        maximum_reservoir_residual = std::max(
            maximum_reservoir_residual,
            std::abs(
                reservoir_closing[static_cast<std::size_t>(reservoir)] -
                reservoir_opening[static_cast<std::size_t>(reservoir)] -
                incoming + outgoing
            )
        );
    }
    step.maximum_absolute_reservoir_transfer_residual_kg = checked_double(
        maximum_reservoir_residual,
        "finite dry-rock accounting reservoir residual overflowed"
    );

    const std::size_t arithmetic_terms =
        step.opening_surface_packets.dry_rock_mass_kg.size() +
        step.transported_surface_packets.dry_rock_mass_kg.size() +
        step.closing_surface_packets.dry_rock_mass_kg.size() +
        step.opening_upper_mantle_packets.dry_rock_mass_kg.size() +
        step.closing_upper_mantle_packets.dry_rock_mass_kg.size() +
        step.proxy_compensation_transfers.dry_rock_mass_kg.size() +
        transport_plan.overlap_area_km2.size() + cell_count + 16;
    const long double accounting_bound = forward_error_bound(
        std::abs(opening_global) + std::abs(closing_global) +
            requested_source_total + requested_sink_total,
        arithmetic_terms
    );
    if (
        std::abs(closing_global - opening_global) > accounting_bound ||
        maximum_origin_residual > accounting_bound ||
        maximum_reservoir_residual > accounting_bound ||
        std::abs(opening_global -
            state.surface_state_envelope_capacity_kg) > accounting_bound ||
        requested_source_total != fulfilled_source_total ||
        requested_sink_total - fulfilled_sink_total > accounting_bound
    ) {
        throw std::runtime_error(
            "finite dry-rock accounting closure invariant failed"
        );
    }
    populate_step_counts(step);
    step.maximum_surface_packet_count_per_owner = static_cast<int>(
        maximum_surface_packet_count_per_owner
    );
    step.maximum_live_reservoir_packet_count = static_cast<int>(
        maximum_live_reservoir_packet_count
    );

    state.surface_packets_by_cell = std::move(surface);
    state.upper_mantle_packets = std::move(mantle);
    state.subducted_slab_packets_by_plate = std::move(slab);
    state.history.push_back(std::move(step));
}

}  // namespace magic_geo::detail
