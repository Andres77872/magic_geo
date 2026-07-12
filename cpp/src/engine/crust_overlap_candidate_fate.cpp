#include "internal.hpp"

namespace magic_geo::detail {
namespace {

constexpr int PERSISTENT_PAIR_ID_BASE = 256;
constexpr std::size_t MAX_MEMBERSHIP_AREA_CLASSES_PER_CELL = 16384;
constexpr std::size_t MAX_BOUNDARY_SEGMENTS_PER_CELL = 8;

constexpr const char* PHYSICAL_NOT_ALL_ACTIVE =
    "not_all_segments_have_active_convergence";
constexpr const char* PHYSICAL_ALL_UNKNOWN =
    "all_active_all_physical_polarities_unknown";
constexpr const char* PHYSICAL_MIXED =
    "all_active_mixed_resolved_and_unknown";
constexpr const char* PHYSICAL_CONFLICT =
    "all_active_resolved_polarities_conflict";
constexpr const char* PHYSICAL_UNIFORM =
    "all_active_resolved_polarity_uniform";

constexpr const char* HEURISTIC_NOT_ALL_ACTIVE =
    "not_all_segments_have_active_convergence";
constexpr const char* HEURISTIC_UNAVAILABLE =
    "all_active_one_or_more_unique_oceanic_candidates_unavailable";
constexpr const char* HEURISTIC_CONFLICT =
    "all_active_unique_oceanic_candidates_conflict";
constexpr const char* HEURISTIC_UNIFORM =
    "all_active_unique_oceanic_candidate_uniform";

constexpr const char* ASSIGNMENT_NONBINARY =
    "unknown_nonbinary_membership";
constexpr const char* ASSIGNMENT_NON_DISTINCT_PAIR =
    "unknown_non_distinct_source_plate_pair";
constexpr const char* ASSIGNMENT_NO_PAIR =
    "unknown_no_same_step_boundary_pair";
constexpr const char* ASSIGNMENT_NO_INCIDENCE =
    "unknown_no_same_step_endpoint_incidence";
constexpr const char* ASSIGNMENT_NO_UNIFORM_EVIDENCE =
    "unknown_no_uniform_pair_polarity_evidence";
constexpr const char* ASSIGNMENT_HEURISTIC =
    "uniform_oceanic_side_heuristic_candidate";
constexpr const char* ASSIGNMENT_PHYSICAL =
    "uniform_resolved_physical_polarity_backed_candidate";

struct PairAccumulator {
    CrustOverlapBoundaryPairEvidence evidence;
    std::set<int> endpoint_cell_ids;
    bool all_active = true;
    int unknown_physical_count = 0;
    int resolved_physical_count = 0;
    bool physical_roles_initialized = false;
    bool physical_roles_conflict = false;
    int physical_subducting_plate_id = -1;
    int physical_overriding_plate_id = -1;
    bool heuristic_candidate_unavailable = false;
    bool heuristic_roles_initialized = false;
    bool heuristic_roles_conflict = false;
    int heuristic_subducting_plate_id = -1;
    int heuristic_overriding_plate_id = -1;
};

int persistent_pair_id(int plate_low_id, int plate_high_id) {
    if (
        plate_low_id < 0 || plate_low_id >= PERSISTENT_PAIR_ID_BASE ||
        plate_high_id <= plate_low_id ||
        plate_high_id >= PERSISTENT_PAIR_ID_BASE
    ) {
        throw std::runtime_error(
            "crust-overlap candidate-fate persistent plate pair is invalid"
        );
    }
    return plate_low_id * PERSISTENT_PAIR_ID_BASE + plate_high_id;
}

double checked_double(long double value, const char* context) {
    if (
        !std::isfinite(value) ||
        value > static_cast<long double>(std::numeric_limits<double>::max()) ||
        value < -static_cast<long double>(std::numeric_limits<double>::max())
    ) {
        throw std::runtime_error(
            std::string("crust-overlap candidate-fate ") + context +
            " is not representable as binary64"
        );
    }
    const double converted = static_cast<double>(value);
    if (!std::isfinite(converted)) {
        throw std::runtime_error(
            std::string("crust-overlap candidate-fate ") + context +
            " conversion is not finite"
        );
    }
    return converted;
}

long double binary64_operation_roundoff_bound(
    std::size_t operation_count,
    long double absolute_operand_sum
) {
    if (
        !std::isfinite(absolute_operand_sum) ||
        absolute_operand_sum < 0.0L
    ) {
        throw std::runtime_error(
            "crust-overlap candidate-fate binary64 operand sum is invalid"
        );
    }
    const long double scaled_epsilon =
        static_cast<long double>(operation_count) *
        static_cast<long double>(std::numeric_limits<double>::epsilon());
    if (!std::isfinite(scaled_epsilon) || scaled_epsilon >= 1.0L) {
        throw std::runtime_error(
            "crust-overlap candidate-fate binary64 operation bound is invalid"
        );
    }
    return scaled_epsilon == 0.0L
        ? 0.0L
        : (scaled_epsilon / (1.0L - scaled_epsilon)) *
            absolute_operand_sum;
}

std::pair<int, int> roles_from_sides(
    const PlateBoundarySegment& segment,
    const std::string& subducting_side,
    const std::string& overriding_side,
    const char* context
) {
    if (subducting_side == "left" && overriding_side == "right") {
        return {segment.left_plate_id, segment.right_plate_id};
    }
    if (subducting_side == "right" && overriding_side == "left") {
        return {segment.right_plate_id, segment.left_plate_id};
    }
    throw std::runtime_error(
        std::string("crust-overlap candidate-fate ") + context +
        " roles are not opposite canonical sides"
    );
}

void merge_roles(
    int subducting_plate_id,
    int overriding_plate_id,
    bool& initialized,
    bool& conflict,
    int& consensus_subducting_plate_id,
    int& consensus_overriding_plate_id
) {
    if (!initialized) {
        consensus_subducting_plate_id = subducting_plate_id;
        consensus_overriding_plate_id = overriding_plate_id;
        initialized = true;
    } else if (
        consensus_subducting_plate_id != subducting_plate_id ||
        consensus_overriding_plate_id != overriding_plate_id
    ) {
        conflict = true;
    }
}

void consume_physical_evidence(
    const PlateBoundarySegment& segment,
    PairAccumulator& pair
) {
    if (!segment.convergence_active) {
        if (
            segment.physical_polarity_status !=
                "not_applicable_no_active_convergence" ||
            segment.physical_polarity_source != "none" ||
            segment.physical_subducting_side != "none" ||
            segment.physical_overriding_side != "none" ||
            segment.physical_polarity_confidence != 0.0
        ) {
            throw std::runtime_error(
                "crust-overlap candidate-fate inactive physical polarity tuple is malformed"
            );
        }
        pair.all_active = false;
        return;
    }

    if (
        segment.physical_polarity_status == "unknown_unresolved" &&
        segment.physical_polarity_source == "none" &&
        segment.physical_subducting_side == "unknown" &&
        segment.physical_overriding_side == "unknown" &&
        segment.physical_polarity_confidence == 0.0
    ) {
        pair.unknown_physical_count++;
        return;
    }

    if (
        segment.physical_polarity_status == "resolved" &&
        (
            segment.physical_polarity_source == "supplied_constraint" ||
            segment.physical_polarity_source == "physical_solver"
        ) &&
        std::isfinite(segment.physical_polarity_confidence) &&
        segment.physical_polarity_confidence > 0.0 &&
        segment.physical_polarity_confidence <= 1.0
    ) {
        const auto [subducting_plate_id, overriding_plate_id] = roles_from_sides(
            segment,
            segment.physical_subducting_side,
            segment.physical_overriding_side,
            "resolved physical polarity"
        );
        merge_roles(
            subducting_plate_id,
            overriding_plate_id,
            pair.physical_roles_initialized,
            pair.physical_roles_conflict,
            pair.physical_subducting_plate_id,
            pair.physical_overriding_plate_id
        );
        pair.resolved_physical_count++;
        return;
    }

    throw std::runtime_error(
        "crust-overlap candidate-fate active physical polarity tuple is malformed"
    );
}

void consume_heuristic_evidence(
    const PlateBoundarySegment& segment,
    PairAccumulator& pair
) {
    if (!segment.convergence_active) {
        if (
            segment.polarity_candidate_status != "no_active_convergence" ||
            segment.candidate_subducting_side != "none" ||
            segment.candidate_overriding_side != "none"
        ) {
            throw std::runtime_error(
                "crust-overlap candidate-fate inactive heuristic tuple is malformed"
            );
        }
        return;
    }

    if (
        segment.polarity_candidate_status == "left_oceanic_only" ||
        segment.polarity_candidate_status == "right_oceanic_only"
    ) {
        const std::string expected_subducting_side =
            segment.polarity_candidate_status == "left_oceanic_only"
                ? "left"
                : "right";
        const std::string expected_overriding_side =
            expected_subducting_side == "left" ? "right" : "left";
        if (
            segment.candidate_subducting_side != expected_subducting_side ||
            segment.candidate_overriding_side != expected_overriding_side
        ) {
            throw std::runtime_error(
                "crust-overlap candidate-fate unique-oceanic heuristic tuple is malformed"
            );
        }
        const auto [subducting_plate_id, overriding_plate_id] = roles_from_sides(
            segment,
            segment.candidate_subducting_side,
            segment.candidate_overriding_side,
            "unique-oceanic heuristic"
        );
        merge_roles(
            subducting_plate_id,
            overriding_plate_id,
            pair.heuristic_roles_initialized,
            pair.heuristic_roles_conflict,
            pair.heuristic_subducting_plate_id,
            pair.heuristic_overriding_plate_id
        );
        return;
    }

    if (
        segment.polarity_candidate_status ==
            "unresolved_missing_opening_crust_state" ||
        segment.polarity_candidate_status == "ambiguous_both_oceanic" ||
        segment.polarity_candidate_status == "unresolved_no_oceanic_side"
    ) {
        if (
            segment.candidate_subducting_side != "none" ||
            segment.candidate_overriding_side != "none"
        ) {
            throw std::runtime_error(
                "crust-overlap candidate-fate unresolved heuristic tuple is malformed"
            );
        }
        pair.heuristic_candidate_unavailable = true;
        return;
    }

    throw std::runtime_error(
        "crust-overlap candidate-fate active heuristic status is invalid"
    );
}

void finalize_pair(PairAccumulator& pair) {
    if (!pair.all_active) {
        pair.evidence.physical_consensus_status = PHYSICAL_NOT_ALL_ACTIVE;
        pair.evidence.heuristic_consensus_status = HEURISTIC_NOT_ALL_ACTIVE;
        return;
    }

    if (
        pair.unknown_physical_count > 0 &&
        pair.resolved_physical_count > 0
    ) {
        pair.evidence.physical_consensus_status = PHYSICAL_MIXED;
    } else if (pair.unknown_physical_count > 0) {
        pair.evidence.physical_consensus_status = PHYSICAL_ALL_UNKNOWN;
    } else if (pair.physical_roles_conflict) {
        pair.evidence.physical_consensus_status = PHYSICAL_CONFLICT;
    } else if (pair.resolved_physical_count > 0) {
        pair.evidence.physical_consensus_status = PHYSICAL_UNIFORM;
        pair.evidence.physical_subducting_plate_id =
            pair.physical_subducting_plate_id;
        pair.evidence.physical_overriding_plate_id =
            pair.physical_overriding_plate_id;
    } else {
        throw std::runtime_error(
            "crust-overlap candidate-fate active pair has no physical evidence"
        );
    }

    if (pair.heuristic_candidate_unavailable) {
        pair.evidence.heuristic_consensus_status = HEURISTIC_UNAVAILABLE;
    } else if (pair.heuristic_roles_conflict) {
        pair.evidence.heuristic_consensus_status = HEURISTIC_CONFLICT;
    } else if (pair.heuristic_roles_initialized) {
        pair.evidence.heuristic_consensus_status = HEURISTIC_UNIFORM;
        pair.evidence.heuristic_subducting_plate_id =
            pair.heuristic_subducting_plate_id;
        pair.evidence.heuristic_overriding_plate_id =
            pair.heuristic_overriding_plate_id;
    } else {
        throw std::runtime_error(
            "crust-overlap candidate-fate active pair has no heuristic evidence"
        );
    }
}

int contributor_for_plate(
    const CrustTransportPlan& transport,
    int contributor_begin,
    int contributor_end,
    int plate_id
) {
    int matching_contributor_id = -1;
    for (int contributor_id = contributor_begin;
         contributor_id < contributor_end;
         ++contributor_id) {
        const std::size_t index = static_cast<std::size_t>(contributor_id);
        if (transport.coverage_membership_area_class_source_plate_ids[index] ==
            plate_id) {
            if (matching_contributor_id != -1) {
                throw std::runtime_error(
                    "crust-overlap candidate-fate contributor plate role is not unique"
                );
            }
            matching_contributor_id = contributor_id;
        }
    }
    if (matching_contributor_id < 0) {
        throw std::runtime_error(
            "crust-overlap candidate-fate contributor plate role is absent"
        );
    }
    return matching_contributor_id;
}

}  // namespace

CrustOverlapCandidateFateLedger build_crust_overlap_candidate_fate_ledger(
    const CrustTransportPlan& transport,
    const std::vector<PlateBoundarySegment>& boundary_segments,
    int step_id,
    int cell_count,
    int plate_count
) {
    if (
        step_id < 0 || cell_count <= 0 || plate_count < 2 ||
        plate_count > PERSISTENT_PAIR_ID_BASE || plate_count >= cell_count
    ) {
        throw std::runtime_error(
            "crust-overlap candidate-fate dimensions are invalid"
        );
    }
    const std::size_t cell_count_size = static_cast<std::size_t>(cell_count);
    if (
        boundary_segments.size() >
            MAX_BOUNDARY_SEGMENTS_PER_CELL * cell_count_size
    ) {
        throw std::runtime_error(
            "crust-overlap candidate-fate boundary segment cap exceeded"
        );
    }

    const std::size_t class_count =
        transport.coverage_membership_area_class_area_km2.size();
    const std::size_t contributor_count =
        transport.coverage_membership_area_class_source_cell_ids.size();
    if (
        class_count > MAX_MEMBERSHIP_AREA_CLASSES_PER_CELL * cell_count_size ||
        class_count > static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
        contributor_count >
            static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
        transport.coverage_membership_area_class_destination_offsets.size() !=
            cell_count_size + 1 ||
        transport.coverage_membership_area_class_count_by_cell.size() !=
            cell_count_size ||
        transport.coverage_arrangement_fragment_count_by_cell.size() !=
            cell_count_size ||
        transport.overlap_excess_area_km2_by_cell.size() != cell_count_size ||
        transport.coverage_membership_area_class_multiplicity.size() !=
            class_count ||
        transport.coverage_membership_area_class_contributor_offsets.size() !=
            class_count + 1 ||
        transport.coverage_membership_area_class_source_cell_ids.size() !=
            transport.coverage_membership_area_class_source_plate_ids.size() ||
        transport.coverage_membership_area_class_destination_offsets.front() !=
            0 ||
        transport.coverage_membership_area_class_destination_offsets.back() !=
            static_cast<int>(class_count) ||
        transport.coverage_membership_area_class_contributor_offsets.front() !=
            0 ||
        transport.coverage_membership_area_class_contributor_offsets.back() !=
            static_cast<int>(
                transport.coverage_membership_area_class_source_cell_ids.size()
            ) ||
        !std::isfinite(transport.global_overlap_excess_area_km2) ||
        transport.global_overlap_excess_area_km2 < 0.0
    ) {
        throw std::runtime_error(
            "crust-overlap candidate-fate membership ledger shape is invalid"
        );
    }

    std::map<std::pair<int, int>, PairAccumulator> pairs;
    for (std::size_t index = 0; index < boundary_segments.size(); ++index) {
        const PlateBoundarySegment& segment = boundary_segments[index];
        if (
            index > static_cast<std::size_t>(std::numeric_limits<int>::max()) ||
            segment.segment_id != static_cast<int>(index) ||
            segment.left_cell_id < 0 || segment.left_cell_id >= cell_count ||
            segment.right_cell_id < 0 || segment.right_cell_id >= cell_count ||
            segment.left_cell_id == segment.right_cell_id ||
            segment.left_plate_id < 0 || segment.left_plate_id >= plate_count ||
            segment.right_plate_id < 0 || segment.right_plate_id >= plate_count ||
            segment.left_plate_id == segment.right_plate_id
        ) {
            throw std::runtime_error(
                "crust-overlap candidate-fate boundary segment identity is invalid"
            );
        }
        const int plate_low_id =
            std::min(segment.left_plate_id, segment.right_plate_id);
        const int plate_high_id =
            std::max(segment.left_plate_id, segment.right_plate_id);
        const std::pair<int, int> key{plate_low_id, plate_high_id};
        PairAccumulator& pair = pairs[key];
        if (pair.evidence.pair_id < 0) {
            pair.evidence.pair_id = persistent_pair_id(
                plate_low_id, plate_high_id
            );
            pair.evidence.plate_low_id = plate_low_id;
            pair.evidence.plate_high_id = plate_high_id;
        }
        pair.evidence.segment_ids.push_back(segment.segment_id);
        pair.endpoint_cell_ids.insert(segment.left_cell_id);
        pair.endpoint_cell_ids.insert(segment.right_cell_id);
        consume_physical_evidence(segment, pair);
        consume_heuristic_evidence(segment, pair);
    }

    CrustOverlapCandidateFateLedger ledger;
    ledger.source_plate_assignment_step_id = step_id == 0 ? 0 : step_id - 1;
    ledger.boundary_plate_assignment_step_id = step_id;
    ledger.boundary_pair_evidence.reserve(pairs.size());
    std::map<int, const PairAccumulator*> pairs_by_id;
    for (auto& [key, pair] : pairs) {
        (void)key;
        finalize_pair(pair);
        if (
            !std::is_sorted(
                pair.evidence.segment_ids.begin(),
                pair.evidence.segment_ids.end()
            ) ||
            !pairs_by_id.emplace(pair.evidence.pair_id, &pair).second
        ) {
            throw std::runtime_error(
                "crust-overlap candidate-fate pair ordering is invalid"
            );
        }
        ledger.boundary_pair_evidence.push_back(pair.evidence);
    }

    long double physical_area_km2 = 0.0L;
    long double heuristic_area_km2 = 0.0L;
    long double unresolved_area_km2 = 0.0L;
    long double all_class_excess_area_km2 = 0.0L;
    long double absolute_class_excess_area_km2 = 0.0L;
    long double validated_row_discrepancy_km2 = 0.0L;
    double replayed_global_overlap_excess_area_km2 = 0.0;
    ledger.overlap_class_candidates.reserve(class_count);
    int previous_class_end = 0;
    for (int destination_cell_id = 0;
         destination_cell_id < cell_count;
         ++destination_cell_id) {
        const int class_begin =
            transport.coverage_membership_area_class_destination_offsets[
                static_cast<std::size_t>(destination_cell_id)
            ];
        const int class_end =
            transport.coverage_membership_area_class_destination_offsets[
                static_cast<std::size_t>(destination_cell_id + 1)
            ];
        if (
            class_begin != previous_class_end || class_end < class_begin ||
            class_end > static_cast<int>(class_count) ||
            class_end - class_begin !=
                transport.coverage_membership_area_class_count_by_cell[
                    static_cast<std::size_t>(destination_cell_id)
                ]
        ) {
            throw std::runtime_error(
                "crust-overlap candidate-fate destination class offsets are invalid"
            );
        }
        previous_class_end = class_end;

        long double destination_class_excess_area_km2 = 0.0L;

        for (int class_id = class_begin; class_id < class_end; ++class_id) {
            const std::size_t class_index = static_cast<std::size_t>(class_id);
            const int multiplicity =
                transport.coverage_membership_area_class_multiplicity[
                    class_index
                ];
            const double area_km2 =
                transport.coverage_membership_area_class_area_km2[class_index];
            const int contributor_begin =
                transport.coverage_membership_area_class_contributor_offsets[
                    class_index
                ];
            const int contributor_end =
                transport.coverage_membership_area_class_contributor_offsets[
                    class_index + 1
                ];
            if (
                !std::isfinite(area_km2) || area_km2 <= 0.0 ||
                multiplicity < 0 || contributor_begin < 0 ||
                contributor_end < contributor_begin ||
                contributor_end > static_cast<int>(
                    transport.coverage_membership_area_class_source_cell_ids.size()
                ) ||
                contributor_end - contributor_begin != multiplicity
            ) {
                throw std::runtime_error(
                    "crust-overlap candidate-fate membership class is invalid"
                );
            }
            int previous_source_cell_id = -1;
            for (int contributor_id = contributor_begin;
                 contributor_id < contributor_end;
                 ++contributor_id) {
                const std::size_t contributor_index =
                    static_cast<std::size_t>(contributor_id);
                const int source_cell_id =
                    transport.coverage_membership_area_class_source_cell_ids[
                        contributor_index
                    ];
                const int source_plate_id =
                    transport.coverage_membership_area_class_source_plate_ids[
                        contributor_index
                    ];
                if (
                    source_cell_id <= previous_source_cell_id ||
                    source_cell_id >= cell_count || source_plate_id < 0 ||
                    source_plate_id >= plate_count
                ) {
                    throw std::runtime_error(
                        "crust-overlap candidate-fate class contributor is invalid"
                    );
                }
                previous_source_cell_id = source_cell_id;
            }

            if (multiplicity < 2) {
                continue;
            }
            CrustOverlapClassCandidate candidate;
            candidate.membership_area_class_id = class_id;
            candidate.destination_cell_id = destination_cell_id;
            candidate.multiplicity = multiplicity;
            const long double excess_area_km2 =
                static_cast<long double>(multiplicity - 1) *
                static_cast<long double>(area_km2);
            if (!std::isfinite(excess_area_km2) || excess_area_km2 <= 0.0L) {
                throw std::runtime_error(
                    "crust-overlap candidate-fate class excess area is invalid"
                );
            }
            destination_class_excess_area_km2 += excess_area_km2;
            all_class_excess_area_km2 += excess_area_km2;
            absolute_class_excess_area_km2 += std::abs(excess_area_km2);

            if (multiplicity != 2) {
                candidate.assignment_status = ASSIGNMENT_NONBINARY;
            } else {
                const int first_plate_id =
                    transport.coverage_membership_area_class_source_plate_ids[
                        static_cast<std::size_t>(contributor_begin)
                    ];
                const int second_plate_id =
                    transport.coverage_membership_area_class_source_plate_ids[
                        static_cast<std::size_t>(contributor_begin + 1)
                    ];
                if (first_plate_id == second_plate_id) {
                    candidate.assignment_status = ASSIGNMENT_NON_DISTINCT_PAIR;
                } else {
                    const int plate_low_id =
                        std::min(first_plate_id, second_plate_id);
                    const int plate_high_id =
                        std::max(first_plate_id, second_plate_id);
                    const int pair_id = persistent_pair_id(
                        plate_low_id, plate_high_id
                    );
                    const auto pair_found = pairs_by_id.find(pair_id);
                    if (pair_found == pairs_by_id.end()) {
                        candidate.assignment_status = ASSIGNMENT_NO_PAIR;
                    } else {
                        candidate.boundary_pair_evidence_id = pair_id;
                        const PairAccumulator& pair = *pair_found->second;
                        if (
                            pair.endpoint_cell_ids.find(destination_cell_id) ==
                                pair.endpoint_cell_ids.end()
                        ) {
                            candidate.assignment_status = ASSIGNMENT_NO_INCIDENCE;
                        } else if (
                            pair.evidence.physical_consensus_status ==
                                PHYSICAL_UNIFORM
                        ) {
                            candidate.assignment_status = ASSIGNMENT_PHYSICAL;
                            candidate.candidate_subducting_contributor_id =
                                contributor_for_plate(
                                    transport,
                                    contributor_begin,
                                    contributor_end,
                                    pair.evidence.physical_subducting_plate_id
                                );
                            candidate.candidate_overriding_contributor_id =
                                contributor_for_plate(
                                    transport,
                                    contributor_begin,
                                    contributor_end,
                                    pair.evidence.physical_overriding_plate_id
                                );
                        } else if (
                            pair.evidence.physical_consensus_status ==
                                PHYSICAL_ALL_UNKNOWN &&
                            pair.evidence.heuristic_consensus_status ==
                                HEURISTIC_UNIFORM
                        ) {
                            candidate.assignment_status = ASSIGNMENT_HEURISTIC;
                            candidate.candidate_subducting_contributor_id =
                                contributor_for_plate(
                                    transport,
                                    contributor_begin,
                                    contributor_end,
                                    pair.evidence.heuristic_subducting_plate_id
                                );
                            candidate.candidate_overriding_contributor_id =
                                contributor_for_plate(
                                    transport,
                                    contributor_begin,
                                    contributor_end,
                                    pair.evidence.heuristic_overriding_plate_id
                                );
                        } else {
                            candidate.assignment_status =
                                ASSIGNMENT_NO_UNIFORM_EVIDENCE;
                        }
                    }
                }
            }

            if (candidate.assignment_status == ASSIGNMENT_PHYSICAL) {
                physical_area_km2 += excess_area_km2;
            } else if (candidate.assignment_status == ASSIGNMENT_HEURISTIC) {
                heuristic_area_km2 += excess_area_km2;
            } else {
                unresolved_area_km2 += excess_area_km2;
            }
            ledger.overlap_class_candidates.push_back(std::move(candidate));
        }

        const double recorded_row_excess_area_km2 =
            transport.overlap_excess_area_km2_by_cell[
                static_cast<std::size_t>(destination_cell_id)
            ];
        if (
            !std::isfinite(recorded_row_excess_area_km2) ||
            recorded_row_excess_area_km2 < 0.0
        ) {
            throw std::runtime_error(
                "crust-overlap candidate-fate recorded destination overlap excess is invalid"
            );
        }
        const long double row_discrepancy_km2 = std::abs(
            destination_class_excess_area_km2 -
            static_cast<long double>(recorded_row_excess_area_km2)
        );
        const std::size_t row_class_count = static_cast<std::size_t>(
            class_end - class_begin
        );
        const int arrangement_fragment_count =
            transport.coverage_arrangement_fragment_count_by_cell[
                static_cast<std::size_t>(destination_cell_id)
            ];
        if (
            arrangement_fragment_count < static_cast<int>(row_class_count) ||
            arrangement_fragment_count >
                static_cast<int>(MAX_MEMBERSHIP_AREA_CLASSES_PER_CELL)
        ) {
            throw std::runtime_error(
                "crust-overlap candidate-fate arrangement fragment count is invalid"
            );
        }
        const std::size_t binary64_operation_count =
            static_cast<std::size_t>(arrangement_fragment_count) * 8 +
            row_class_count * 8 + 16;
        const long double row_operation_bound_km2 =
            binary64_operation_roundoff_bound(
                binary64_operation_count,
                std::abs(destination_class_excess_area_km2) +
                std::abs(static_cast<long double>(recorded_row_excess_area_km2))
            );
        if (row_discrepancy_km2 > row_operation_bound_km2) {
            throw std::runtime_error(
                "crust-overlap candidate-fate destination binary64 excess discrepancy is invalid"
            );
        }
        validated_row_discrepancy_km2 += row_discrepancy_km2;
        replayed_global_overlap_excess_area_km2 +=
            recorded_row_excess_area_km2;
    }

    if (
        replayed_global_overlap_excess_area_km2 !=
            transport.global_overlap_excess_area_km2
    ) {
        throw std::runtime_error(
            "crust-overlap candidate-fate global overlap row replay did not close exactly"
        );
    }

    const long double accounted_area_km2 =
        physical_area_km2 + heuristic_area_km2 + unresolved_area_km2;
    const long double partition_residual_km2 =
        accounted_area_km2 -
        static_cast<long double>(transport.global_overlap_excess_area_km2);
    const long double operation_bound_km2 =
        binary64_operation_roundoff_bound(
        class_count * 16 + cell_count_size * 16 + 64,
        absolute_class_excess_area_km2 * 4.0L +
            std::abs(accounted_area_km2) +
            std::abs(all_class_excess_area_km2) +
            std::abs(static_cast<long double>(
                transport.global_overlap_excess_area_km2
            )) +
            validated_row_discrepancy_km2
        );
    if (
        std::abs(accounted_area_km2 - all_class_excess_area_km2) >
            operation_bound_km2 ||
        std::abs(partition_residual_km2) >
            validated_row_discrepancy_km2 + operation_bound_km2
    ) {
        throw std::runtime_error(
            "crust-overlap candidate-fate area partition exceeded its validated-row and operation bound: "
            "partition_residual_km2=" + std::to_string(
                static_cast<double>(partition_residual_km2)
            ) + ", validated_row_discrepancy_km2=" + std::to_string(
                static_cast<double>(validated_row_discrepancy_km2)
            ) + ", operation_bound_km2=" + std::to_string(
                static_cast<double>(operation_bound_km2)
            ) + ", category_partition_delta_km2=" + std::to_string(
                static_cast<double>(
                    accounted_area_km2 - all_class_excess_area_km2
                )
            )
        );
    }
    ledger.physical_polarity_backed_candidate_excess_area_km2 =
        checked_double(physical_area_km2, "physical candidate area");
    ledger.oceanic_heuristic_candidate_excess_area_km2 =
        checked_double(heuristic_area_km2, "heuristic candidate area");
    ledger.unresolved_candidate_excess_area_km2 =
        checked_double(unresolved_area_km2, "unresolved candidate area");
    ledger.accounted_overlap_excess_area_km2 =
        checked_double(accounted_area_km2, "accounted overlap area");
    ledger.candidate_partition_residual_km2 =
        checked_double(partition_residual_km2, "candidate partition residual");

    return ledger;
}

}  // namespace magic_geo::detail
