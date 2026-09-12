#pragma once
#include "model.hpp"
#include "settlement_climate_support.hpp"
#include <cmath>
#include <algorithm>
#include <stdexcept>
namespace magic_geo::detail {
inline bool social_mode(const SocialAvailability* availability) {
    return availability != nullptr && availability->enabled;
}
// Validate the exact existing native source, never infer availability from score zero.
inline bool social_site_available(const Cell& cell) {
    if (!std::isfinite(cell.temperature_c) || !std::isfinite(cell.settlement_score) ||
        !std::isfinite(cell.area_km2) || cell.area_km2 < 0.0 ||
        cell.settlement_score < 0.0 || cell.settlement_score > 1.0 ||
        cell.settlement_climate_supported != settlement_annual_climate_supported(cell.temperature_c)) {
        throw std::runtime_error("invalid native social settlement source");
    }
    if (cell.is_water || cell.is_lake) {
        if (cell.settlement_score != 0.0) throw std::runtime_error("nonzero structural water site source");
        return true;
    }
    if (!cell.settlement_climate_supported && cell.settlement_score != 0.0) {
        throw std::runtime_error("unsupported settlement source is not the zero sentinel");
    }
    return cell.settlement_climate_supported;
}
inline void social_cells_preflight(const std::vector<Cell>& cells) {
    for (std::size_t i = 0; i < cells.size(); ++i) {
        const auto& c = cells[i];
        if (c.id != static_cast<int>(i)) throw std::runtime_error("invalid social cell identity");
        (void)social_site_available(c);  // validates availability, does not impose it
        for (const double value : {c.fertility, c.elevation_m, c.runoff_mm_y,
                c.precipitation_mm_y, c.ice_thickness_m, c.boundary_convergent,
                c.boundary_transform, c.lat, c.lon, c.p.x, c.p.y, c.p.z}) {
            if (!std::isfinite(value)) throw std::runtime_error("nonfinite native social physical source");
        }
        for (int id : c.neighbors) {
            if (id < 0 || id >= static_cast<int>(cells.size())) throw std::runtime_error("invalid social neighbor identity");
        }
    }
}
inline bool social_conflict_exposure_available(const SocialAvailability& availability, int region_id) {
    // A global top-K ranking can affect every candidate-bearing pair. A region
    // absent from all borders has known zero exposure even if another pair fails.
    if (availability.conflict_inference_available) return true;
    return !std::binary_search(availability.conflict_candidate_region_ids.begin(),
        availability.conflict_candidate_region_ids.end(), region_id);
}
}  // namespace magic_geo::detail
