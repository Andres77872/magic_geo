#include "engine/internal.hpp"

#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>

using magic_geo::detail::CrustOverlapCandidateFateLedger;
using magic_geo::detail::CrustTransportPlan;
using magic_geo::detail::PlateBoundarySegment;
using magic_geo::detail::build_crust_overlap_candidate_fate_ledger;

namespace {

#define CHECK(condition)                                                        \
    do {                                                                        \
        if (!(condition)) {                                                     \
            std::cerr << "CHECK failed at line " << __LINE__ << ": "          \
                      << #condition << '\n';                                    \
            return false;                                                       \
        }                                                                       \
    } while (false)

struct ClassSpec {
    int destination_cell_id = 0;
    double area_km2 = 0.0;
    std::vector<int> source_cell_ids;
    std::vector<int> source_plate_ids;
};

CrustTransportPlan make_plan(
    int cell_count,
    const std::vector<ClassSpec>& classes
) {
    CrustTransportPlan plan;
    plan.coverage_membership_area_class_destination_offsets.assign(
        static_cast<std::size_t>(cell_count + 1), 0
    );
    plan.coverage_membership_area_class_count_by_cell.assign(
        static_cast<std::size_t>(cell_count), 0
    );
    plan.overlap_excess_area_km2_by_cell.assign(
        static_cast<std::size_t>(cell_count), 0.0
    );
    plan.coverage_arrangement_fragment_count_by_cell.assign(
        static_cast<std::size_t>(cell_count), 0
    );
    plan.coverage_membership_area_class_contributor_offsets.push_back(0);
    int previous_destination = -1;
    for (const ClassSpec& spec : classes) {
        if (
            spec.destination_cell_id < previous_destination ||
            spec.destination_cell_id < 0 ||
            spec.destination_cell_id >= cell_count ||
            spec.source_cell_ids.size() != spec.source_plate_ids.size()
        ) {
            throw std::runtime_error("invalid test class specification");
        }
        previous_destination = spec.destination_cell_id;
        plan.coverage_membership_area_class_area_km2.push_back(spec.area_km2);
        const int multiplicity = static_cast<int>(spec.source_cell_ids.size());
        plan.coverage_membership_area_class_multiplicity.push_back(multiplicity);
        plan.coverage_membership_area_class_source_cell_ids.insert(
            plan.coverage_membership_area_class_source_cell_ids.end(),
            spec.source_cell_ids.begin(),
            spec.source_cell_ids.end()
        );
        plan.coverage_membership_area_class_source_plate_ids.insert(
            plan.coverage_membership_area_class_source_plate_ids.end(),
            spec.source_plate_ids.begin(),
            spec.source_plate_ids.end()
        );
        plan.coverage_membership_area_class_contributor_offsets.push_back(
            static_cast<int>(
                plan.coverage_membership_area_class_source_cell_ids.size()
            )
        );
        plan.coverage_membership_area_class_count_by_cell[
            static_cast<std::size_t>(spec.destination_cell_id)
        ]++;
        plan.coverage_arrangement_fragment_count_by_cell[
            static_cast<std::size_t>(spec.destination_cell_id)
        ]++;
        if (multiplicity >= 2) {
            plan.overlap_excess_area_km2_by_cell[
                static_cast<std::size_t>(spec.destination_cell_id)
            ] += static_cast<double>(multiplicity - 1) * spec.area_km2;
        }
    }
    int class_offset = 0;
    for (int cell_id = 0; cell_id < cell_count; ++cell_id) {
        plan.coverage_membership_area_class_destination_offsets[
            static_cast<std::size_t>(cell_id)
        ] = class_offset;
        class_offset += plan.coverage_membership_area_class_count_by_cell[
            static_cast<std::size_t>(cell_id)
        ];
    }
    plan.coverage_membership_area_class_destination_offsets.back() =
        class_offset;
    for (double row_excess_area_km2 : plan.overlap_excess_area_km2_by_cell) {
        plan.global_overlap_excess_area_km2 += row_excess_area_km2;
    }
    return plan;
}

PlateBoundarySegment active_segment(
    int segment_id,
    int left_cell_id,
    int right_cell_id,
    int left_plate_id,
    int right_plate_id,
    int heuristic_subducting_plate_id
) {
    PlateBoundarySegment segment;
    segment.segment_id = segment_id;
    segment.left_cell_id = left_cell_id;
    segment.right_cell_id = right_cell_id;
    segment.left_plate_id = left_plate_id;
    segment.right_plate_id = right_plate_id;
    segment.convergence_active = true;
    segment.physical_polarity_status = "unknown_unresolved";
    segment.physical_polarity_source = "none";
    segment.physical_subducting_side = "unknown";
    segment.physical_overriding_side = "unknown";
    segment.physical_polarity_confidence = 0.0;
    if (heuristic_subducting_plate_id == left_plate_id) {
        segment.polarity_candidate_status = "left_oceanic_only";
        segment.candidate_subducting_side = "left";
        segment.candidate_overriding_side = "right";
    } else if (heuristic_subducting_plate_id == right_plate_id) {
        segment.polarity_candidate_status = "right_oceanic_only";
        segment.candidate_subducting_side = "right";
        segment.candidate_overriding_side = "left";
    } else {
        throw std::runtime_error("invalid heuristic subducting test plate");
    }
    return segment;
}

PlateBoundarySegment inactive_segment(
    int segment_id,
    int left_cell_id,
    int right_cell_id,
    int left_plate_id,
    int right_plate_id
) {
    PlateBoundarySegment segment;
    segment.segment_id = segment_id;
    segment.left_cell_id = left_cell_id;
    segment.right_cell_id = right_cell_id;
    segment.left_plate_id = left_plate_id;
    segment.right_plate_id = right_plate_id;
    segment.convergence_active = false;
    segment.physical_polarity_status =
        "not_applicable_no_active_convergence";
    segment.physical_polarity_source = "none";
    segment.physical_subducting_side = "none";
    segment.physical_overriding_side = "none";
    segment.physical_polarity_confidence = 0.0;
    segment.polarity_candidate_status = "no_active_convergence";
    segment.candidate_subducting_side = "none";
    segment.candidate_overriding_side = "none";
    return segment;
}

void resolve_physical(
    PlateBoundarySegment& segment,
    int subducting_plate_id,
    const char* source = "physical_solver"
) {
    segment.physical_polarity_status = "resolved";
    segment.physical_polarity_source = source;
    segment.physical_polarity_confidence = 0.75;
    if (subducting_plate_id == segment.left_plate_id) {
        segment.physical_subducting_side = "left";
        segment.physical_overriding_side = "right";
    } else if (subducting_plate_id == segment.right_plate_id) {
        segment.physical_subducting_side = "right";
        segment.physical_overriding_side = "left";
    } else {
        throw std::runtime_error("invalid physical subducting test plate");
    }
}

template <typename Function>
bool throws_runtime_error(Function&& function) {
    try {
        function();
    } catch (const std::runtime_error&) {
        return true;
    }
    return false;
}

bool sparse_status_precedence_and_partition_close() {
    const CrustTransportPlan plan = make_plan(8, {
        {0, 3.0, {4, 5}, {0, 1}},
        {0, 2.0, {0, 1, 2}, {0, 1, 2}},
        {1, 1.0, {0, 3}, {0, 0}},
        {2, 4.0, {2, 3}, {2, 3}},
        {3, 5.0, {4, 5}, {0, 1}},
        {4, 6.0, {1, 6}, {1, 3}},
    });
    const std::vector<PlateBoundarySegment> segments = {
        active_segment(0, 0, 6, 0, 1, 0),
        active_segment(1, 4, 7, 1, 0, 0),
        inactive_segment(2, 2, 6, 2, 3),
    };
    const CrustOverlapCandidateFateLedger ledger =
        build_crust_overlap_candidate_fate_ledger(
            plan, segments, 1, 8, 4
        );

    CHECK(ledger.source_plate_assignment_step_id == 0);
    CHECK(ledger.boundary_plate_assignment_step_id == 1);
    CHECK(ledger.boundary_pair_evidence.size() == 2);
    CHECK(ledger.boundary_pair_evidence[0].pair_id == 1);
    CHECK(ledger.boundary_pair_evidence[0].segment_ids ==
        std::vector<int>({0, 1}));
    CHECK(ledger.boundary_pair_evidence[0].physical_consensus_status ==
        "all_active_all_physical_polarities_unknown");
    CHECK(ledger.boundary_pair_evidence[0].heuristic_consensus_status ==
        "all_active_unique_oceanic_candidate_uniform");
    CHECK(ledger.boundary_pair_evidence[0].heuristic_subducting_plate_id == 0);
    CHECK(ledger.boundary_pair_evidence[0].heuristic_overriding_plate_id == 1);
    CHECK(ledger.boundary_pair_evidence[1].pair_id == 515);
    CHECK(ledger.boundary_pair_evidence[1].physical_consensus_status ==
        "not_all_segments_have_active_convergence");

    CHECK(ledger.overlap_class_candidates.size() == 6);
    CHECK(ledger.overlap_class_candidates[0].assignment_status ==
        "uniform_oceanic_side_heuristic_candidate");
    CHECK(ledger.overlap_class_candidates[0].boundary_pair_evidence_id == 1);
    CHECK(ledger.overlap_class_candidates[0]
        .candidate_subducting_contributor_id == 0);
    CHECK(ledger.overlap_class_candidates[0]
        .candidate_overriding_contributor_id == 1);
    CHECK(ledger.overlap_class_candidates[1].assignment_status ==
        "unknown_nonbinary_membership");
    CHECK(ledger.overlap_class_candidates[2].assignment_status ==
        "unknown_non_distinct_source_plate_pair");
    CHECK(ledger.overlap_class_candidates[3].assignment_status ==
        "unknown_no_uniform_pair_polarity_evidence");
    CHECK(ledger.overlap_class_candidates[3].boundary_pair_evidence_id == 515);
    CHECK(ledger.overlap_class_candidates[4].assignment_status ==
        "unknown_no_same_step_endpoint_incidence");
    CHECK(ledger.overlap_class_candidates[4].boundary_pair_evidence_id == 1);
    CHECK(ledger.overlap_class_candidates[5].assignment_status ==
        "unknown_no_same_step_boundary_pair");
    CHECK(ledger.overlap_class_candidates[5].boundary_pair_evidence_id == -1);
    CHECK(ledger.physical_polarity_backed_candidate_excess_area_km2 == 0.0);
    CHECK(ledger.oceanic_heuristic_candidate_excess_area_km2 == 3.0);
    CHECK(ledger.unresolved_candidate_excess_area_km2 == 20.0);
    CHECK(ledger.accounted_overlap_excess_area_km2 == 23.0);
    CHECK(ledger.candidate_partition_residual_km2 == 0.0);
    return true;
}

bool resolved_physical_evidence_has_priority() {
    const CrustTransportPlan plan = make_plan(6, {
        {0, 0.5, {0}, {1}},
        {0, 7.0, {2, 5}, {0, 1}},
    });
    std::vector<PlateBoundarySegment> segments = {
        active_segment(0, 0, 4, 0, 1, 1),
        active_segment(1, 3, 0, 1, 0, 1),
    };
    segments[0].direct_boundary_class = "transform";
    segments[0].direct_transform_strength = 0.9;
    resolve_physical(segments[0], 0, "supplied_constraint");
    resolve_physical(segments[1], 0, "physical_solver");
    const CrustOverlapCandidateFateLedger ledger =
        build_crust_overlap_candidate_fate_ledger(
            plan, segments, 2, 6, 2
        );
    CHECK(ledger.source_plate_assignment_step_id == 1);
    CHECK(ledger.boundary_plate_assignment_step_id == 2);
    CHECK(ledger.boundary_pair_evidence[0].physical_consensus_status ==
        "all_active_resolved_polarity_uniform");
    CHECK(ledger.boundary_pair_evidence[0].heuristic_consensus_status ==
        "all_active_unique_oceanic_candidate_uniform");
    CHECK(ledger.overlap_class_candidates[0].assignment_status ==
        "uniform_resolved_physical_polarity_backed_candidate");
    // Global contributor ids point into the source-cell/source-plate CSR,
    // not into the class-local slice and not to source cell ids.
    CHECK(ledger.overlap_class_candidates[0]
        .candidate_subducting_contributor_id == 1);
    CHECK(ledger.overlap_class_candidates[0]
        .candidate_overriding_contributor_id == 2);
    CHECK(ledger.physical_polarity_backed_candidate_excess_area_km2 == 7.0);
    CHECK(ledger.oceanic_heuristic_candidate_excess_area_km2 == 0.0);
    CHECK(ledger.unresolved_candidate_excess_area_km2 == 0.0);
    return true;
}

bool mixed_or_conflicting_physical_evidence_blocks_heuristic_fallback() {
    const CrustTransportPlan plan = make_plan(6, {
        {0, 2.5, {2, 5}, {0, 1}},
    });
    std::vector<PlateBoundarySegment> mixed = {
        active_segment(0, 0, 4, 0, 1, 0),
        active_segment(1, 3, 0, 1, 0, 0),
    };
    resolve_physical(mixed[0], 0);
    CrustOverlapCandidateFateLedger ledger =
        build_crust_overlap_candidate_fate_ledger(plan, mixed, 0, 6, 2);
    CHECK(ledger.boundary_pair_evidence[0].physical_consensus_status ==
        "all_active_mixed_resolved_and_unknown");
    CHECK(ledger.overlap_class_candidates[0].assignment_status ==
        "unknown_no_uniform_pair_polarity_evidence");
    CHECK(ledger.unresolved_candidate_excess_area_km2 == 2.5);

    std::vector<PlateBoundarySegment> conflicting = mixed;
    resolve_physical(conflicting[1], 1);
    ledger = build_crust_overlap_candidate_fate_ledger(
        plan, conflicting, 0, 6, 2
    );
    CHECK(ledger.boundary_pair_evidence[0].physical_consensus_status ==
        "all_active_resolved_polarities_conflict");
    CHECK(ledger.overlap_class_candidates[0].assignment_status ==
        "unknown_no_uniform_pair_polarity_evidence");
    return true;
}

bool heuristic_unavailability_and_conflict_are_pair_wide() {
    const CrustTransportPlan plan = make_plan(6, {
        {0, 1.0, {2, 5}, {0, 1}},
    });
    std::vector<PlateBoundarySegment> unavailable = {
        active_segment(0, 0, 4, 0, 1, 0),
        active_segment(1, 3, 0, 1, 0, 0),
    };
    unavailable[1].polarity_candidate_status = "ambiguous_both_oceanic";
    unavailable[1].candidate_subducting_side = "none";
    unavailable[1].candidate_overriding_side = "none";
    CrustOverlapCandidateFateLedger ledger =
        build_crust_overlap_candidate_fate_ledger(
            plan, unavailable, 0, 6, 2
        );
    CHECK(ledger.boundary_pair_evidence[0].heuristic_consensus_status ==
        "all_active_one_or_more_unique_oceanic_candidates_unavailable");
    CHECK(ledger.overlap_class_candidates[0].assignment_status ==
        "unknown_no_uniform_pair_polarity_evidence");

    std::vector<PlateBoundarySegment> conflicting = {
        active_segment(0, 0, 4, 0, 1, 0),
        active_segment(1, 3, 0, 1, 0, 1),
    };
    ledger = build_crust_overlap_candidate_fate_ledger(
        plan, conflicting, 0, 6, 2
    );
    CHECK(ledger.boundary_pair_evidence[0].heuristic_consensus_status ==
        "all_active_unique_oceanic_candidates_conflict");
    CHECK(ledger.overlap_class_candidates[0].assignment_status ==
        "unknown_no_uniform_pair_polarity_evidence");
    return true;
}

bool identity_step_and_tiny_positive_area_are_preserved() {
    const double tiny_area = std::numeric_limits<double>::denorm_min();
    CrustTransportPlan plan = make_plan(4, {
        {0, tiny_area, {1, 2}, {0, 1}},
    });
    const std::vector<PlateBoundarySegment> segments = {
        active_segment(0, 0, 3, 0, 1, 0),
    };
    const CrustOverlapCandidateFateLedger ledger =
        build_crust_overlap_candidate_fate_ledger(plan, segments, 0, 4, 2);
    CHECK(ledger.source_plate_assignment_step_id == 0);
    CHECK(ledger.boundary_plate_assignment_step_id == 0);
    CHECK(ledger.oceanic_heuristic_candidate_excess_area_km2 == tiny_area);
    CHECK(ledger.accounted_overlap_excess_area_km2 == tiny_area);
    return true;
}

bool malformed_inputs_fail_closed() {
    const CrustTransportPlan valid_plan = make_plan(5, {
        {0, 1.0, {1, 2}, {0, 1}},
    });
    const std::vector<PlateBoundarySegment> valid_segments = {
        active_segment(0, 0, 3, 0, 1, 0),
    };
    CHECK(throws_runtime_error([&] {
        build_crust_overlap_candidate_fate_ledger(
            valid_plan, valid_segments, 0, 5, 257
        );
    }));
    CHECK(throws_runtime_error([&] {
        build_crust_overlap_candidate_fate_ledger(
            valid_plan, valid_segments, -1, 5, 2
        );
    }));

    CrustTransportPlan bad_area = valid_plan;
    bad_area.coverage_membership_area_class_area_km2[0] =
        std::numeric_limits<double>::quiet_NaN();
    CHECK(throws_runtime_error([&] {
        build_crust_overlap_candidate_fate_ledger(
            bad_area, valid_segments, 0, 5, 2
        );
    }));

    CrustTransportPlan bad_offsets = valid_plan;
    bad_offsets.coverage_membership_area_class_contributor_offsets.back() = 3;
    CHECK(throws_runtime_error([&] {
        build_crust_overlap_candidate_fate_ledger(
            bad_offsets, valid_segments, 0, 5, 2
        );
    }));

    CrustTransportPlan corrupted_row = valid_plan;
    corrupted_row.overlap_excess_area_km2_by_cell[0] +=
        4096.0 * std::numeric_limits<double>::epsilon();
    corrupted_row.global_overlap_excess_area_km2 =
        corrupted_row.overlap_excess_area_km2_by_cell[0];
    CHECK(throws_runtime_error([&] {
        build_crust_overlap_candidate_fate_ledger(
            corrupted_row, valid_segments, 0, 5, 2
        );
    }));

    std::vector<PlateBoundarySegment> bad_segment_id = valid_segments;
    bad_segment_id[0].segment_id = 7;
    CHECK(throws_runtime_error([&] {
        build_crust_overlap_candidate_fate_ledger(
            valid_plan, bad_segment_id, 0, 5, 2
        );
    }));

    std::vector<PlateBoundarySegment> malformed_physical = valid_segments;
    malformed_physical[0].physical_polarity_confidence = 0.1;
    CHECK(throws_runtime_error([&] {
        build_crust_overlap_candidate_fate_ledger(
            valid_plan, malformed_physical, 0, 5, 2
        );
    }));

    std::vector<PlateBoundarySegment> malformed_heuristic = valid_segments;
    malformed_heuristic[0].candidate_subducting_side = "right";
    CHECK(throws_runtime_error([&] {
        build_crust_overlap_candidate_fate_ledger(
            valid_plan, malformed_heuristic, 0, 5, 2
        );
    }));
    return true;
}

}  // namespace

int main() {
    if (
        !sparse_status_precedence_and_partition_close() ||
        !resolved_physical_evidence_has_priority() ||
        !mixed_or_conflicting_physical_evidence_blocks_heuristic_fallback() ||
        !heuristic_unavailability_and_conflict_are_pair_wide() ||
        !identity_step_and_tiny_positive_area_are_preserved() ||
        !malformed_inputs_fail_closed()
    ) {
        return 1;
    }
    return 0;
}
