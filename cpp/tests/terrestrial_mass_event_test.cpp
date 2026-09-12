#include "terrestrial_calorimeter/cryosphere_enthalpy.hpp"

#include <algorithm>
#include <bit>
#include <cfloat>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <limits>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>

#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 &&                  \
    LDBL_MAX_EXP >= 16384
namespace c = cryosphere_prototype;
namespace {
constexpr int mass_call_cap = 32;
constexpr int advance_call_cap = 4;
int checks = 0, mass_calls = 0, advance_calls = 0;
std::vector<std::string> observations;

// These are API-shape checks, not a zero-duration convention in disguise.
template <class T>
concept HasDuration = requires(T x) { x.duration_seconds; };
template <class T>
concept HasHeatFlux = requires(T x) { x.net_heat_flux_w_m2; };
template <class T>
concept HasHeatAmount = requires(T x) { x.prescribed_heat_j; };
template <class T>
concept HasHeatDensity = requires(T x) { x.prescribed_heat_j_m2; };
static_assert(!HasDuration<c::MassEventInput> && !HasHeatFlux<c::MassEventInput>);
static_assert(!HasHeatAmount<c::MassEventResult> && !HasHeatDensity<c::MassEventLedger>);

void check(bool condition, const char *message) {
    ++checks;
    if (!condition)
        throw std::runtime_error(message);
}

std::string json_quote(const std::string &value) {
    std::ostringstream out;
    out << '"';
    for (unsigned char ch : value) {
        if (ch == '"' || ch == '\\')
            out << '\\' << ch;
        else if (ch < 32)
            out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << int(ch);
        else
            out << ch;
    }
    out << '"';
    return out.str();
}

std::string number(double value) {
    std::ostringstream out;
    if (std::isfinite(value))
        out << std::setprecision(17) << value;
    else
        out << "{\"nonfinite_binary64_bits\":\"" << std::hex << std::bit_cast<std::uint64_t>(value)
            << "\"}";
    return out.str();
}

template <class T, class F> std::string array(const std::vector<T> &values, F write) {
    std::string result = "[";
    for (std::size_t i = 0; i < values.size(); ++i) {
        if (i)
            result += ',';
        result += write(values[i]);
    }
    return result + ']';
}

std::string state_json(const c::State &value) {
    return "{\"water_mass_kg_m2\":" + number(value.water_mass_kg_m2) +
           ",\"enthalpy_j_m2\":" + number(value.enthalpy_j_m2) + '}';
}

std::string request_json(const c::WaterProperties &p, const std::vector<c::Column> &columns,
                         const std::vector<c::State> &initial, const c::MassEventInput &input) {
    return "{\"water\":{\"freezing_temperature_k\":" + number(p.freezing_temperature_k) +
           ",\"solid_heat_capacity_j_kg_k\":" + number(p.solid_heat_capacity_j_kg_k) +
           ",\"liquid_heat_capacity_j_kg_k\":" + number(p.liquid_heat_capacity_j_kg_k) +
           ",\"latent_heat_j_kg\":" + number(p.latent_heat_j_kg) + "},\"columns\":" +
           array(columns,
                 [](const c::Column &x) {
                     return "{\"area_m2\":" + number(x.area_m2) +
                            ",\"dry_heat_capacity_j_m2_k\":" + number(x.dry_heat_capacity_j_m2_k) +
                            '}';
                 }) +
           ",\"initial\":" + array(initial, state_json) + ",\"input\":{\"imports\":" +
           array(input.imports,
                 [](const c::Import &x) {
                     return "{\"recipient\":" + std::to_string(x.recipient) +
                            ",\"phase\":" + std::to_string(static_cast<int>(x.phase)) +
                            ",\"mass_kg\":" + number(x.mass_kg) +
                            ",\"temperature_k\":" + number(x.temperature_k) + '}';
                 }) +
           ",\"exports\":" +
           array(input.exports,
                 [](const c::Export &x) {
                     return "{\"donor\":" + std::to_string(x.donor) +
                            ",\"phase\":" + std::to_string(static_cast<int>(x.phase)) +
                            ",\"mass_kg\":" + number(x.mass_kg) + '}';
                 }) +
           ",\"transfers\":" +
           array(input.transfers,
                 [](const c::Transfer &x) {
                     return "{\"donor\":" + std::to_string(x.donor) +
                            ",\"recipient\":" + std::to_string(x.recipient) +
                            ",\"phase\":" + std::to_string(static_cast<int>(x.phase)) +
                            ",\"mass_kg\":" + number(x.mass_kg) + '}';
                 }) +
           "}}";
}

template <class T> std::string result_json(const T &result) {
    std::string out =
        "{\"state\":" + array(result.state, state_json) + ",\"phase\":" +
        array(result.phase,
              [](const c::PhaseState &x) {
                  return "{\"temperature_k\":" + number(x.temperature_k) +
                         ",\"solid_mass_kg_m2\":" + number(x.solid_mass_kg_m2) +
                         ",\"liquid_mass_kg_m2\":" + number(x.liquid_mass_kg_m2) + '}';
              }) +
        ",\"movements\":" +
        array(result.movements,
              [](const c::Movement &x) {
                  return "{\"donor\":" + std::to_string(x.donor) +
                         ",\"recipient\":" + std::to_string(x.recipient) +
                         ",\"phase\":" + std::to_string(static_cast<int>(x.phase)) +
                         ",\"mass_kg\":" + number(x.mass_kg) +
                         ",\"temperature_k\":" + number(x.temperature_k) +
                         ",\"specific_enthalpy_j_kg\":" + number(x.specific_enthalpy_j_kg) +
                         ",\"carried_enthalpy_j\":" + number(x.carried_enthalpy_j) + '}';
              }) +
        ",\"ledger\":" + array(result.ledger, [](const auto &x) {
            std::string row =
                "{\"imported_mass_kg_m2\":" + number(x.imported_mass_kg_m2) +
                ",\"exported_mass_kg_m2\":" + number(x.exported_mass_kg_m2) +
                ",\"imported_enthalpy_j_m2\":" + number(x.imported_enthalpy_j_m2) +
                ",\"exported_enthalpy_j_m2\":" + number(x.exported_enthalpy_j_m2) +
                ",\"mass_residual_kg_m2\":" + number(x.mass_residual_kg_m2) +
                ",\"energy_residual_j_m2\":" + number(x.energy_residual_j_m2) +
                ",\"mass_roundoff_allowance_kg_m2\":" + number(x.mass_roundoff_allowance_kg_m2) +
                ",\"energy_roundoff_allowance_j_m2\":" + number(x.energy_roundoff_allowance_j_m2);
            if constexpr (HasHeatDensity<decltype(x)>)
                row += ",\"prescribed_heat_j_m2\":" + number(x.prescribed_heat_j_m2);
            return row + '}';
        });
    out += ",\"global_mass_change_kg\":" + number(result.global_mass_change_kg) +
           ",\"external_net_mass_kg\":" + number(result.external_net_mass_kg) +
           ",\"global_mass_residual_kg\":" + number(result.global_mass_residual_kg) +
           ",\"global_mass_roundoff_allowance_kg\":" +
           number(result.global_mass_roundoff_allowance_kg) +
           ",\"global_energy_change_j\":" + number(result.global_energy_change_j) +
           ",\"external_net_enthalpy_j\":" + number(result.external_net_enthalpy_j) +
           ",\"global_energy_residual_j\":" + number(result.global_energy_residual_j) +
           ",\"global_energy_roundoff_allowance_j\":" +
           number(result.global_energy_roundoff_allowance_j);
    if constexpr (HasHeatAmount<T>)
        out += ",\"prescribed_heat_j\":" + number(result.prescribed_heat_j);
    return out + '}';
}

std::optional<c::MassEventResult> invoke(const char *id, const c::WaterProperties &p,
                                         const std::vector<c::Column> &columns,
                                         const std::vector<c::State> &initial,
                                         const c::MassEventInput &input,
                                         const char *refusal = nullptr) {
    check(mass_calls < mass_call_cap, "mass event call cap");
    const std::string before = request_json(p, columns, initial, input);
    std::optional<c::MassEventResult> result;
    std::string error;
    ++mass_calls;
    try {
        result = c::apply_mass_events(p, columns, initial, input);
    } catch (const c::Error &e) {
        error = e.what();
    }
    const std::string after = request_json(p, columns, initial, input);
    observations.push_back(
        "{\"id\":" + json_quote(id) + ",\"operation\":\"apply_mass_events\",\"before\":" + before +
        ",\"after\":" + after + ",\"status\":" + json_quote(result ? "accepted" : "refused") +
        ",\"error\":" + (error.empty() ? "null" : json_quote(error)) +
        ",\"result\":" + (result ? result_json(*result) : "null") + '}');
    check(before == after, "mass event mutated its input");
    if (refusal) {
        check(!result && error.find(refusal) != std::string::npos,
              "missing or wrong mass event refusal");
    } else {
        check(result.has_value(), "unexpected mass event refusal");
        check(result->state.size() == columns.size() && result->phase.size() == columns.size() &&
                  result->ledger.size() == columns.size(),
              "mass event result coverage");
        for (const auto &row : result->ledger) {
            check(std::abs(row.mass_residual_kg_m2) <= row.mass_roundoff_allowance_kg_m2 &&
                      std::abs(row.energy_residual_j_m2) <= row.energy_roundoff_allowance_j_m2,
                  "local canonical closure");
        }
        check(std::abs(result->global_mass_residual_kg) <=
                      result->global_mass_roundoff_allowance_kg &&
                  std::abs(result->global_energy_residual_j) <=
                      result->global_energy_roundoff_allowance_j,
              "global canonical closure");
    }
    return result;
}

c::StepResult old_advance(const char *id, const c::WaterProperties &p,
                          const std::vector<c::Column> &columns,
                          const std::vector<c::State> &initial, const c::StepInput &input) {
    check(advance_calls < advance_call_cap, "advance call cap");
    const auto snapshot = [&] {
        return "{\"mass_request\":" +
               request_json(p, columns, initial, {input.imports, input.exports, input.transfers}) +
               ",\"duration_seconds\":" + number(input.duration_seconds) +
               ",\"net_heat_flux_w_m2\":" + array(input.net_heat_flux_w_m2, number) + '}';
    };
    const auto before = snapshot();
    ++advance_calls;
    std::optional<c::StepResult> result;
    std::string error;
    try {
        result = c::advance(p, columns, initial, input);
    } catch (const c::Error &e) {
        error = e.what();
    }
    const auto after = snapshot();
    observations.push_back(
        "{\"id\":" + json_quote(id) + ",\"operation\":\"advance\",\"before\":" + before +
        ",\"after\":" + after + ",\"status\":" + json_quote(result ? "accepted" : "refused") +
        ",\"error\":" + (error.empty() ? "null" : json_quote(error)) +
        ",\"result\":" + (result ? result_json(*result) : "null") + '}');
    check(before == after, "advance mutated its input");
    check(result.has_value(), "unexpected advance refusal");
    return *result;
}

void run() {
    const c::WaterProperties p{8, 2, 4, 16};
    const std::vector<c::Column> one{{2, 1}};
    const std::vector<c::State> dry{{0, 0}};
    const std::vector<c::State> mixed{{2, 16}};
    const std::vector<c::Column> two{{2, 1}, {4, 1}};
    const std::vector<c::State> pair{{2, 16}, {0, 0}};
    const auto cold =
        invoke("cold_solid_import", p, one, dry, {{{0, c::Phase::solid, 4, 4}}, {}, {}});
    check(cold->state[0] == c::State{2, -16} && cold->external_net_enthalpy_j == -32,
          "cold import must carry its signed sensible enthalpy");
    check(cold->phase[0].solid_mass_kg_m2 == 2 && cold->phase[0].liquid_mass_kg_m2 == 0,
          "cold solid phase inventory");
    const auto warm =
        invoke("warm_liquid_import", p, one, dry, {{{0, c::Phase::liquid, 1, 10}}, {}, {}});
    check(warm->state[0] == c::State{0.5, 12} && warm->movements[0].carried_enthalpy_j == 24,
          "warm liquid import enthalpy");
    const auto exchange = invoke("initial_mixed_export_and_import", p, one, mixed,
                                 {{{0, c::Phase::solid, 1, 8}}, {{0, c::Phase::liquid, 1}}, {}});
    check(exchange->state[0] == c::State{2, 8} && exchange->external_net_mass_kg == 0 &&
              exchange->external_net_enthalpy_j == -16,
          "mass-balanced event can export energy");

    const auto moved =
        invoke("unequal_area_transfer", p, two, pair, {{}, {}, {{0, 1, c::Phase::liquid, 1}}});
    check(moved->state[0] == c::State{1.5, 8} && moved->state[1] == c::State{0.25, 4},
          "unequal area transfer normalization");
    check(moved->ledger[0].exported_enthalpy_j_m2 * 2 == 16 &&
              moved->ledger[1].imported_enthalpy_j_m2 * 4 == 16 &&
              moved->global_mass_change_kg == 0 && moved->global_energy_change_j == 0 &&
              moved->external_net_mass_kg == 0 && moved->external_net_enthalpy_j == 0,
          "internal transfer must use one canonical debit and credit");
    const auto exact =
        invoke("exact_initial_liquid_limit", p, one, mixed, {{}, {{0, c::Phase::liquid, 2}}, {}});
    check(exact->state[0] == c::State{1, 0}, "exact gross initial inventory must be allowed");
    invoke("one_ulp_excess_liquid", p, one, mixed,
           {{}, {{0, c::Phase::liquid, std::nextafter(2.0, 3.0)}}, {}},
           "insufficient initial liquid");
    invoke("gross_withdrawals_not_net", p, two, pair,
           {{{0, c::Phase::liquid, 2, 8}},
            {{0, c::Phase::liquid, 1.5}},
            {{0, 1, c::Phase::liquid, 1}}},
           "insufficient initial liquid");
    invoke("import_cannot_refeed", p, one, dry,
           {{{0, c::Phase::liquid, 1, 8}}, {{0, c::Phase::liquid, 1}}, {}},
           "insufficient initial liquid");
    invoke("transfer_cannot_refeed", p, {{2, 1}, {4, 1}, {1, 1}}, {{2, 16}, {0, 0}, {0, 0}},
           {{}, {}, {{0, 1, c::Phase::liquid, 1}, {1, 2, c::Phase::liquid, 1}}},
           "insufficient initial liquid");
    invoke("wrong_donor_phase", p, one, {{2, 0}}, {{}, {{0, c::Phase::liquid, 1}}, {}},
           "insufficient initial liquid");

    c::MassEventInput ordered{
        {{0, c::Phase::solid, 1, 8}, {1, c::Phase::liquid, 0.25, 9}, {0, c::Phase::solid, 0.5, 6}},
        {{0, c::Phase::liquid, 0.25}, {0, c::Phase::liquid, 0.5}},
        {{0, 1, c::Phase::solid, 0.25}, {0, 1, c::Phase::liquid, 0.5}}};
    const auto forward = invoke("canonical_order_forward", p, two, pair, ordered);
    std::reverse(ordered.imports.begin(), ordered.imports.end());
    std::reverse(ordered.exports.begin(), ordered.exports.end());
    std::reverse(ordered.transfers.begin(), ordered.transfers.end());
    const auto reverse = invoke("canonical_order_reverse", p, two, pair, ordered);
    check(result_json(*forward) == result_json(*reverse), "canonical permutation result changed");

    const std::vector<c::State> signed_zero{{0, -0.0}, {0.125, 0.3}};
    const auto identity = invoke("empty_validated_identity", p, two, signed_zero, {});
    check(array(identity->state, state_json) == array(signed_zero, state_json) &&
              std::signbit(identity->state[0].enthalpy_j_m2),
          "empty event rounded the initial state");
    check(identity->movements.empty() && identity->global_mass_change_kg == 0 &&
              identity->global_energy_change_j == 0 &&
              identity->global_energy_roundoff_allowance_j == 0,
          "empty event is not exact identity");

    auto bad_p = p;
    bad_p.latent_heat_j_kg = 0;
    invoke("invalid_properties", bad_p, one, dry, {}, "latent_heat");
    invoke("invalid_area", p, {{0, 1}}, dry, {}, "area_m2");
    invoke("invalid_negative_water", p, one, {{-1, 0}}, {}, "water_mass");
    invoke("invalid_coverage", p, two, dry, {}, "coverage mismatch");
    invoke("zero_mass", p, one, dry, {{{0, c::Phase::solid, 0, 8}}, {}, {}}, "movement.mass_kg");
    invoke("solid_above_freezing", p, one, dry, {{{0, c::Phase::solid, 1, 9}}, {}, {}},
           "warmer than freezing");
    invoke("invalid_phase", p, one, dry, {{{0, static_cast<c::Phase>(17), 1, 8}}, {}, {}},
           "unsupported phase");
    invoke("invalid_index", p, one, dry, {{{1, c::Phase::solid, 1, 8}}, {}, {}},
           "unknown cell index");
    invoke("self_transfer", p, one, mixed, {{}, {}, {{0, 0, c::Phase::solid, 1}}}, "self transfer");
    invoke("nonfinite_mass", p, one, dry,
           {{{0, c::Phase::solid, std::numeric_limits<double>::infinity(), 8}}, {}, {}},
           "movement.mass_kg");
    invoke("empty_invalid_temperature", p, one, {{0, -9}}, {}, "negative absolute temperature");
    invoke("late_invalid_recipient", p, two, pair,
           {{{0, c::Phase::solid, 1, 8}, {2, c::Phase::solid, 1, 8}}, {}, {}},
           "unknown cell index");
    invoke("one_ulp_excess_solid", p, one, mixed,
           {{}, {{0, c::Phase::solid, std::nextafter(2.0, 3.0)}}, {}},
           "insufficient initial solid");
    invoke("negative_import_temperature", p, one, dry, {{{0, c::Phase::solid, 1, -1}}, {}, {}},
           "import.temperature");
    invoke("empty_columns", p, {}, {}, {}, "nonempty bounded array");
    invoke("invalid_dry_capacity", p, {{2, 0}}, dry, {}, "dry_heat_capacity");

    // The mass API exposes a rounded event state. The old combined API retains
    // the +1 in its private expansion until it cancels the subsequent heat.
    const c::WaterProperties unit{1, 1, 1, 1};
    const std::vector<c::Column> unit_column{{1, 1}};
    const double large = 0x1p53;
    const std::vector<c::State> large_initial{{0, large}};
    const c::MassEventInput addition{{{0, c::Phase::liquid, 1, 1}}, {}, {}};
    const auto rounded =
        invoke("mass_event_2pow53_plus_1", unit, unit_column, large_initial, addition);
    check(rounded->state[0] == c::State{1, large} &&
              rounded->ledger[0].energy_residual_j_m2 == -1 &&
              rounded->global_energy_change_j == 0 && rounded->external_net_enthalpy_j == 1 &&
              rounded->global_energy_residual_j == -1,
          "mass event concealed its one-joule rounding residual");
    const auto combined = old_advance("original_combined_cancellation", unit, unit_column,
                                      large_initial, {1, {-large}, addition.imports, {}, {}});
    check(combined.state[0] == c::State{1, 1} && combined.global_energy_residual_j == 0,
          "advance lost its unrounded mass-event energy before heat");
    const auto split = old_advance("explicit_rounded_public_composition", unit, unit_column,
                                   rounded->state, {1, {-large}, {}, {}, {}});
    check(split.state[0] == c::State{1, 0}, "public event composition discriminator");
    check(mass_calls <= mass_call_cap && advance_calls <= advance_call_cap, "final call bounds");
}
} // namespace

int main() {
    std::string error;
    try {
        run();
    } catch (const std::exception &e) {
        error = e.what();
    }
    std::cout << "{\"schema\":\"terrestrial_mass_event_controls_v1\","
                 "\"capability_available\":true,"
              << "\"passed\":" << (error.empty() ? "true" : "false") << ",\"checks\":" << checks
              << ",\"mass_event_calls\":" << mass_calls << ",\"advance_calls\":" << advance_calls
              << ",\"mass_event_call_cap\":" << mass_call_cap
              << ",\"advance_call_cap\":" << advance_call_cap
              << ",\"observations\":" << array(observations, [](const std::string &x) { return x; })
              << ",\"error\":" << (error.empty() ? "null" : json_quote(error)) << "}\n";
    return error.empty() ? 0 : 1;
}
#else
int main() {
    std::cout << "{\"schema\":\"terrestrial_mass_event_controls_v1\","
                 "\"capability_available\":false,"
                 "\"status\":\"unsupported_backend_skipped\",\"mass_event_"
                 "calls\":0,\"advance_calls\":0}\n";
    return 0;
}
#endif
