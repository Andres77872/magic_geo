#pragma once
#include "model.hpp"
#include "terrestrial_calorimeter/cryosphere_enthalpy.hpp"
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

namespace magic_geo::detail {

struct TerrestrialWaterError : std::runtime_error {
    std::string code;
    TerrestrialWaterError(std::string code, std::string message);
};
struct TerrestrialWaterCapability {
    bool available;
    std::string reason;
};
TerrestrialWaterCapability terrestrial_water_capability();

// Capture only after completed surface/lake classification. Captured cells are
// immutable; this is a fixed-terrain epoch context, not a climate-cache entry.
class TerrestrialSurfaceSnapshot {
  public:
    std::uint64_t surface_revision() const;
    const std::vector<Cell> &cells() const;

  private:
    struct Data;
    std::shared_ptr<const Data> data_;
    explicit TerrestrialSurfaceSnapshot(std::shared_ptr<const Data>);
    friend TerrestrialSurfaceSnapshot capture_terrestrial_surface(const std::vector<Cell> &,
                                                                  std::uint64_t);
    friend bool same_terrestrial_surface_epoch(const TerrestrialSurfaceSnapshot &,
                                               const TerrestrialSurfaceSnapshot &);
    friend class TerrestrialWaterOwner;
};
TerrestrialSurfaceSnapshot capture_terrestrial_surface(const std::vector<Cell> &cells,
                                                       std::uint64_t surface_revision = 0);
bool same_terrestrial_surface_epoch(const TerrestrialSurfaceSnapshot &,
                                    const TerrestrialSurfaceSnapshot &);
bool terrestrial_surface_matches(const TerrestrialSurfaceSnapshot &, const std::vector<Cell> &);

struct TerrestrialWaterLimits {
    std::size_t max_cells = 4096;
    std::size_t max_committed_intervals = 128;
    std::size_t max_events_per_interval = 8192;
    std::size_t max_consumed_event_ids = 65536;
    std::size_t max_identifier_bytes = 96;
};
struct TerrestrialWaterProperties {
    cryosphere_prototype::WaterProperties water;
    double reference_water_density_kg_m3;
    double year_duration_seconds;
    std::vector<double> dry_heat_capacity_j_m2_k; // Complete native cell coverage.
};
struct TerrestrialWaterRestart {
    std::uint64_t revision = 0;
    double elapsed_seconds = 0;
    std::vector<cryosphere_prototype::State> state; // W/H, including zero wet slots.
    std::vector<std::string> consumed_event_ids;
};
struct TerrestrialPrecipitationImport {
    std::string id;
    int cell_id;
    cryosphere_prototype::Phase phase;
    double mass_kg;
    double temperature_k;
};
struct TerrestrialLiquidWithdrawal {
    std::string id;
    int cell_id;
    double mass_kg;
};
struct TerrestrialIntervalRequest {
    std::uint64_t expected_revision;
    double duration_seconds;
    std::vector<double> net_heat_flux_w_m2; // Complete coverage; wet entries zero.
    std::vector<TerrestrialPrecipitationImport> precipitation_imports;
    std::vector<TerrestrialLiquidWithdrawal> initial_liquid_withdrawals;
};
struct TerrestrialLiquidHandoff {
    std::string id;
    int cell_id;
    double mass_kg;
    double carried_enthalpy_j; // Actual A export debit; never re-multiplied.
    std::size_t kernel_movement_index;
};
struct TerrestrialLiquidSupplyCell {
    int cell_id;
    bool applicable;
    double original_precipitation_mm_y;
    double delivered_liquid_mass_kg;
    double delivered_liquid_enthalpy_j;
    double delivered_liquid_depth_mm;
    double liquid_supply_mm_y; // Explicit annualization, not precipitation.
    double actual_evapotranspiration_mm;
    double infiltration_mm;
    double runoff_mm;
    double partition_residual_mm;
};
struct TerrestrialLiquidSupplyProjection {
    std::vector<TerrestrialLiquidSupplyCell> cells;
    // Projection-only cell copies. Normal generated cells are never overwritten.
    std::vector<Cell> projected_cells;
};
TerrestrialLiquidSupplyProjection project_terrestrial_liquid_supply(
    const TerrestrialSurfaceSnapshot &, const std::vector<TerrestrialLiquidHandoff> &,
    double duration_seconds, double reference_water_density_kg_m3, double year_duration_seconds);

struct TerrestrialIntervalReceipt {
    std::uint64_t surface_revision;
    TerrestrialWaterProperties properties;
    TerrestrialWaterLimits limits;
    std::vector<Cell> surface_cells; // Original fixed inputs, not projection.
    TerrestrialWaterRestart initial;
    TerrestrialIntervalRequest request;
    TerrestrialWaterRestart final;
    std::vector<int> kernel_column_cell_ids;
    cryosphere_prototype::StepResult kernel_result;
    std::vector<TerrestrialLiquidHandoff> liquid_outbox;
    TerrestrialLiquidSupplyProjection projection;
};
// Opaque prepared state bound to one exact owning restart/context. A caller
// cannot forge or edit its accepted state, outbox or projection before commit.
class TerrestrialIntervalCandidate {
  public:
    const TerrestrialIntervalReceipt &receipt() const;

  private:
    struct Data;
    std::shared_ptr<const Data> data_;
    explicit TerrestrialIntervalCandidate(std::shared_ptr<const Data>);
    friend class TerrestrialWaterOwner;
};
class TerrestrialWaterOwner {
  public:
    TerrestrialWaterOwner(TerrestrialSurfaceSnapshot, TerrestrialWaterProperties,
                          TerrestrialWaterRestart, TerrestrialWaterLimits = {});
    ~TerrestrialWaterOwner();
    TerrestrialWaterOwner(TerrestrialWaterOwner &&) noexcept;
    TerrestrialWaterOwner &operator=(TerrestrialWaterOwner &&) noexcept;
    TerrestrialWaterOwner(const TerrestrialWaterOwner &) = delete;
    TerrestrialWaterOwner &operator=(const TerrestrialWaterOwner &) = delete;
    const TerrestrialWaterRestart &restart() const;
    const TerrestrialIntervalReceipt *last_receipt() const;
    const TerrestrialSurfaceSnapshot &surface() const;
    const TerrestrialWaterProperties &properties() const;
    const TerrestrialWaterLimits &limits() const;
    TerrestrialIntervalCandidate prepare(const TerrestrialIntervalRequest &) const;
    void commit(const TerrestrialIntervalCandidate &);

  private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
std::string terrestrial_water_context_json(const TerrestrialWaterOwner &);
std::string terrestrial_interval_request_json(const TerrestrialIntervalRequest &);
std::string terrestrial_water_restart_json(const TerrestrialWaterRestart &);
std::string terrestrial_interval_receipt_json(const TerrestrialIntervalReceipt &);
std::string terrestrial_water_model_json();

} // namespace magic_geo::detail
