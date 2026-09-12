#pragma once

#include <string>

namespace magic_geo::detail {

class PrescribedSeasonalClimateCache;

struct SerializedSeasonalEnergy {
    std::string model;
    std::string forcing_intervals;
    std::string transport_edges;
    std::string balance_records;
};

// Serialize the privately owned, verified cycle. All physical/numerical
// witnesses use round-trip binary64 precision, independent of display options.
// An empty cache is an error; legacy diagnostics cannot stand in for a solve.
SerializedSeasonalEnergy serialize_prescribed_seasonal_energy(
    const PrescribedSeasonalClimateCache& cache
);

}  // namespace magic_geo::detail
