#include "seasonal_climate_cache.hpp"

#include "types/core.hpp"

#include <array>
#include <limits>
#include <stdexcept>
#include <utility>

namespace magic_geo::detail {

struct PrescribedSeasonalClimateCache::State {
    struct CellInput {
        int id;
        std::array<double, 3> point;
        double area_km2;
        std::vector<std::array<double, 3>> control_volume_vertices;
        std::vector<int> control_volume_edge_neighbor_ids;
        double latitude_rad;
        double elevation_m;
        double water_depth_m;
        bool is_water;
        bool is_lake;
        int water_body;

        explicit CellInput(const Cell& cell)
            : id(cell.id), point{cell.p.x, cell.p.y, cell.p.z}, area_km2(cell.area_km2),
              control_volume_edge_neighbor_ids(cell.control_volume_edge_neighbor_ids),
              latitude_rad(cell.lat), elevation_m(cell.elevation_m), water_depth_m(cell.water_depth_m),
              is_water(cell.is_water), is_lake(cell.is_lake), water_body(cell.water_body) {
            control_volume_vertices.reserve(cell.control_volume_vertices.size());
            for (const Vec3 vertex : cell.control_volume_vertices) {
                control_volume_vertices.push_back({vertex.x, vertex.y, vertex.z});
            }
        }

        bool matches(const Cell& cell) const {
            if (id != cell.id || point != std::array<double, 3>{cell.p.x, cell.p.y, cell.p.z} ||
                area_km2 != cell.area_km2 || control_volume_vertices.size() != cell.control_volume_vertices.size() ||
                control_volume_edge_neighbor_ids != cell.control_volume_edge_neighbor_ids ||
                latitude_rad != cell.lat || elevation_m != cell.elevation_m || water_depth_m != cell.water_depth_m ||
                is_water != cell.is_water || is_lake != cell.is_lake || water_body != cell.water_body) {
                return false;
            }
            for (std::size_t i = 0; i < control_volume_vertices.size(); ++i) {
                const Vec3 vertex = cell.control_volume_vertices[i];
                if (control_volume_vertices[i] != std::array<double, 3>{vertex.x, vertex.y, vertex.z}) {
                    return false;
                }
            }
            return true;
        }
    };

    int mesh_backend;
    PrescribedSeasonalClimateOptions requested_options;
    std::vector<CellInput> inputs;
    PrescribedSeasonalClimate result;
    std::size_t completed_solves;
    bool warm_started;

    State(int backend, const std::vector<Cell>& cells,
          const PrescribedSeasonalClimateOptions& options,
          PrescribedSeasonalClimate solved, std::size_t solve_count, bool warm)
        : mesh_backend(backend), requested_options(options), result(std::move(solved)),
          completed_solves(solve_count), warm_started(warm) {
        inputs.reserve(cells.size());
        for (const Cell& cell : cells) inputs.emplace_back(cell);
    }

    bool matches(int backend, const std::vector<Cell>& cells,
                 const PrescribedSeasonalClimateOptions& options) const {
        if (mesh_backend != backend || requested_options != options || inputs.size() != cells.size()) return false;
        for (std::size_t i = 0; i < cells.size(); ++i) {
            if (!inputs[i].matches(cells[i])) return false;
        }
        return true;
    }
};

PrescribedSeasonalClimateCache::PrescribedSeasonalClimateCache() = default;
PrescribedSeasonalClimateCache::~PrescribedSeasonalClimateCache() = default;
PrescribedSeasonalClimateCache::PrescribedSeasonalClimateCache(PrescribedSeasonalClimateCache&&) noexcept = default;
PrescribedSeasonalClimateCache& PrescribedSeasonalClimateCache::operator=(PrescribedSeasonalClimateCache&&) noexcept = default;

const PrescribedSeasonalClimate& PrescribedSeasonalClimateCache::solve(
    int mesh_backend,
    const std::vector<Cell>& cells,
    const PrescribedSeasonalClimateOptions& options
) {
    if (state_ && state_->matches(mesh_backend, cells, options)) return state_->result;
    const std::size_t previous_solves = completed_solve_count();
    if (previous_solves == std::numeric_limits<std::size_t>::max()) {
        throw std::overflow_error("seasonal climate cache solve count is exhausted");
    }
    const bool warm = state_ && state_->result.solution.year.initial_temperature_k.size() == cells.size();
    const std::vector<double> empty_initial;
    const auto& initial = warm ? state_->result.solution.year.initial_temperature_k : empty_initial;
    auto solved = solve_prescribed_seasonal_climate(mesh_backend, cells, options, initial);

    // Key/result copies and allocations complete before publishing anything.
    // The const allocation makes the privately owned certificate immutable;
    // no caller-supplied result or mutable reference can replace its contents.
    auto replacement = std::make_unique<const State>(
        mesh_backend, cells, options, std::move(solved), previous_solves + 1, warm
    );
    state_.swap(replacement);  // Nothrow commit; failures above retain old state.
    return state_->result;
}

const PrescribedSeasonalClimate* PrescribedSeasonalClimateCache::last_result() const noexcept {
    return state_ ? &state_->result : nullptr;
}

std::size_t PrescribedSeasonalClimateCache::completed_solve_count() const noexcept {
    return state_ ? state_->completed_solves : 0;
}

bool PrescribedSeasonalClimateCache::last_solve_was_warm_started() const noexcept {
    return state_ && state_->warm_started;
}

}  // namespace magic_geo::detail
