#pragma once

#include "engine/model.hpp"

#include <string>
#include <vector>

namespace magic_geo::detail {

// Device-produced, diagnostic-only replay of the continuous extensive-state
// reduction over an already authoritative CPU spherical-overlap CSR.  These
// values are compared and discarded; they never replace CrustTransportPlan
// fields or mutate Cell state.
struct CrustOverlapContinuousShadowResult {
    std::vector<double> crust_volume_km3_by_destination;
    std::vector<double> density_weighted_crust_volume_by_destination;
    std::vector<double> crust_age_volume_moment_by_destination;
    std::vector<double> remapped_crust_thickness_km_by_destination;
    std::vector<double> remapped_crust_density_by_destination;
    std::vector<double> remapped_crust_age_ma_by_destination;
};

struct CrustOverlapContinuousShadowValidation {
    bool passed = false;
    std::string failure;

    double maximum_crust_volume_error_km3 = 0.0;
    double maximum_crust_volume_error_bound_km3 = 0.0;
    double maximum_density_weighted_volume_error = 0.0;
    double maximum_density_weighted_volume_error_bound = 0.0;
    double maximum_crust_age_volume_moment_error = 0.0;
    double maximum_crust_age_volume_moment_error_bound = 0.0;
    double maximum_remapped_thickness_error_km = 0.0;
    double maximum_remapped_thickness_error_bound_km = 0.0;
    double maximum_remapped_density_error = 0.0;
    double maximum_remapped_density_error_bound = 0.0;
    double maximum_remapped_age_error_ma = 0.0;
    double maximum_remapped_age_error_bound_ma = 0.0;
    double maximum_error_to_bound_ratio = 0.0;
};

void validate_crust_overlap_continuous_shadow_input(
    const CrustTransportPlan& transport,
    const std::vector<Cell>& cells,
    const std::vector<double>& source_crust_thickness_km,
    const std::vector<double>& source_crust_density,
    const std::vector<double>& source_crust_age_ma
);

CrustOverlapContinuousShadowResult replay_crust_overlap_continuous_reduction_cpu(
    const CrustTransportPlan& transport,
    const std::vector<Cell>& cells,
    const std::vector<double>& source_crust_thickness_km,
    const std::vector<double>& source_crust_density,
    const std::vector<double>& source_crust_age_ma
);

CrustOverlapContinuousShadowValidation
validate_crust_overlap_continuous_shadow_result(
    const CrustTransportPlan& transport,
    const std::vector<Cell>& cells,
    const std::vector<double>& source_crust_thickness_km,
    const std::vector<double>& source_crust_density,
    const std::vector<double>& source_crust_age_ma,
    const CrustOverlapContinuousShadowResult& actual
);

}  // namespace magic_geo::detail
