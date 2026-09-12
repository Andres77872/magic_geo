#pragma once

#include "seasonal_climate.hpp"

#include <cstddef>
#include <memory>
#include <vector>

namespace magic_geo::detail {

// Owns one immutable verified result and its exact relevant input snapshot.
// It never accepts a caller-owned result as an accuracy certificate. Options
// include all physical/source/accuracy/work controls by defaulted equality.
// Geometry, latitude and fresh marine inputs compare without tolerances;
// unrelated later diagnostics and the unused generic neighbor list are ignored.
// This object and input cells must not be concurrently mutated during solve().
class PrescribedSeasonalClimateCache {
public:
    PrescribedSeasonalClimateCache();
    ~PrescribedSeasonalClimateCache();
    PrescribedSeasonalClimateCache(const PrescribedSeasonalClimateCache&) = delete;
    PrescribedSeasonalClimateCache& operator=(const PrescribedSeasonalClimateCache&) = delete;
    PrescribedSeasonalClimateCache(PrescribedSeasonalClimateCache&&) noexcept;
    PrescribedSeasonalClimateCache& operator=(PrescribedSeasonalClimateCache&&) noexcept;

    // A miss fully solves/rechecks the new problem. The preceding phase is
    // only a starting iterate when its cell count matches. Failure preserves
    // the preceding result/key/generation. Returned references remain valid
    // across hits and failures, until a successful miss replaces the entry.
    const PrescribedSeasonalClimate& solve(
        int mesh_backend,
        const std::vector<Cell>& cells,
        const PrescribedSeasonalClimateOptions& options = {}
    );

    const PrescribedSeasonalClimate* last_result() const noexcept;
    std::size_t completed_solve_count() const noexcept;
    // Reports the last completed numerical solve, unchanged by cache hits.
    bool last_solve_was_warm_started() const noexcept;

private:
    struct State;
    std::unique_ptr<const State> state_;
};

}  // namespace magic_geo::detail
