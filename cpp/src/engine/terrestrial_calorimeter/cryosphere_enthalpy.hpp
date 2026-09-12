#pragma once

#include <cstddef>
#include <stdexcept>
#include <vector>

namespace cryosphere_prototype {

// Homogeneous freshwater/mineral-slab calorimeter only. No atmosphere,
// radiation law, snow density, glacier dynamics, ocean or hydrology producer.
struct WaterProperties {
    double freezing_temperature_k;
    double solid_heat_capacity_j_kg_k;
    double liquid_heat_capacity_j_kg_k;
    double latent_heat_j_kg;
};

struct Column {
    double area_m2;
    double dry_heat_capacity_j_m2_k;
};

struct State {
    double water_mass_kg_m2;
    // Relative to dry slab and solid water at the shared freezing temperature.
    double enthalpy_j_m2;
    bool operator==(const State&) const = default;
};

enum class Phase { solid, liquid };

struct PhaseState {
    double temperature_k;
    double solid_mass_kg_m2;
    double liquid_mass_kg_m2;
};

struct Import {
    std::size_t recipient;
    Phase phase;
    double mass_kg;
    double temperature_k;
};

struct Export {
    std::size_t donor;
    Phase phase;
    double mass_kg;
};

struct Transfer {
    std::size_t donor;
    std::size_t recipient;
    Phase phase;
    double mass_kg;
};

struct StepInput {
    double duration_seconds;
    std::vector<double> net_heat_flux_w_m2;
    std::vector<Import> imports;
    std::vector<Export> exports;
    std::vector<Transfer> transfers;
};

struct Movement {
    // -1 denotes the external boundary; at least one end is a real column.
    int donor;
    int recipient;
    Phase phase;
    double mass_kg;
    // Rounded diagnostics; carried enthalpy is rounded from the retained
    // temperature offset/reference expression, not reconstructed from these.
    double temperature_k;
    double specific_enthalpy_j_kg;
    double carried_enthalpy_j;
};

struct Ledger {
    double imported_mass_kg_m2;
    double exported_mass_kg_m2;
    double imported_enthalpy_j_m2;
    double exported_enthalpy_j_m2;
    double prescribed_heat_j_m2;
    // Actual represented-state minus recorded-input residuals; never corrected.
    double mass_residual_kg_m2;
    double energy_residual_j_m2;
    double mass_roundoff_allowance_kg_m2;
    double energy_roundoff_allowance_j_m2;
};

struct StepResult {
    std::vector<State> state;
    std::vector<PhaseState> phase;
    std::vector<Movement> movements;
    std::vector<Ledger> ledger;
    double global_mass_change_kg;
    double external_net_mass_kg;
    double global_mass_residual_kg;
    double global_mass_roundoff_allowance_kg;
    double global_energy_change_j;
    double external_net_enthalpy_j;
    double prescribed_heat_j;
    double global_energy_residual_j;
    double global_energy_roundoff_allowance_j;
};

// A simultaneous mass event has no physical duration and supplies no heat.
// Its output is a newly represented state, not the unrounded intermediate of
// advance(). A caller that needs no event should carry its thermal state
// directly; an empty batch here is a validated, bit-preserving identity.
struct MassEventInput {
    std::vector<Import> imports;
    std::vector<Export> exports;
    std::vector<Transfer> transfers;
};

struct MassEventLedger {
    double imported_mass_kg_m2;
    double exported_mass_kg_m2;
    double imported_enthalpy_j_m2;
    double exported_enthalpy_j_m2;
    // Represented-state minus recorded-input residuals; never corrected.
    double mass_residual_kg_m2;
    double energy_residual_j_m2;
    double mass_roundoff_allowance_kg_m2;
    double energy_roundoff_allowance_j_m2;
};

struct MassEventResult {
    std::vector<State> state;
    std::vector<PhaseState> phase;
    std::vector<Movement> movements;
    std::vector<MassEventLedger> ledger;
    double global_mass_change_kg;
    double external_net_mass_kg;
    double global_mass_residual_kg;
    double global_mass_roundoff_allowance_kg;
    double global_energy_change_j;
    double external_net_enthalpy_j;
    double global_energy_residual_j;
    double global_energy_roundoff_allowance_j;
};

class Error : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

PhaseState phase_state(const WaterProperties&, const Column&, const State&);

// Shared water properties/reference across every column. All gross withdrawals
// use INITIAL donor phase inventories and enthalpies simultaneously. Imports
// cannot refeed exports. Then prescribed constant heat*duration is applied.
// Melt becomes exportable on a later step. Canonical transfer summation makes
// physical output independent of request order. This is a first-order split.
// Pure result construction: every exception leaves all caller input unchanged.
StepResult advance(const WaterProperties&, const std::vector<Column>&,
                   const std::vector<State>&, const StepInput&);

// Initial donor phase inventories and enthalpies govern ALL gross withdrawals,
// including internal transfers; incoming mass cannot fund another withdrawal
// in the same event. Canonical carried enthalpy is shared by each donor/receiver
// pair. All validation and result construction are private: exceptions leave
// every input unchanged. No clock, air state, source IDs or owner is mutated.
// The ledger certifies canonical accounting with explicit rounding residuals;
// it does not bound original-source representation error. In particular,
// apply_mass_events() followed by heating is NOT an equivalent implementation
// of advance(): advance() retains unrounded event energy through its heat sum.
MassEventResult apply_mass_events(const WaterProperties&, const std::vector<Column>&,
                                 const std::vector<State>&, const MassEventInput&);

// Explicit generalized entry for layered water storage. C may be zero only
// while W remains positive before and after the event. The default entry above
// retains its positive-C contract. Empty pure-water nodes require a separate
// atomic topology operation; this entry refuses them and never inserts epsilon.
MassEventResult apply_mass_events_pure_water(const WaterProperties&, const std::vector<Column>&,
                                            const std::vector<State>&, const MassEventInput&);

}  // namespace cryosphere_prototype
