#include "phase_segment.hpp"

#include <cmath>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>
#include <stdexcept>

namespace phase_segment_prototype {
namespace {
namespace t = higher_order_thermal_prototype;
struct Json {
    std::ostringstream out;
    Json() { out.imbue(std::locale::classic()); }
    void value(bool x) { out << (x ? "true" : "false"); }
    void value(int x) { out << x; }
    void value(double x) {
        if (!std::isfinite(x))
            throw std::runtime_error("nonfinite JSON value");
        std::ostringstream scalar;
        scalar.imbue(std::locale::classic());
        scalar << std::setprecision(std::numeric_limits<double>::max_digits10) << x;
        const auto text = scalar.str();
        out << text;
        if (text.find_first_of(".eE") == std::string::npos)
            out << ".0";
    }
    void value(const std::string &x) {
        out << '"';
        const char *hex = "0123456789abcdef";
        for (unsigned char c : x) {
            if (c == '"' || c == '\\')
                out << '\\' << c;
            else if (c < 32)
                out << "\\u00" << hex[c >> 4] << hex[c & 15];
            else
                out << c;
        }
        out << '"';
    }
    void value(const char *x) { value(std::string(x)); }
    void key(const char *name, bool first = false) {
        if (!first)
            out << ',';
        value(name);
        out << ':';
    }
    template <class T> void member(const char *name, const T &x, bool first = false) {
        key(name, first);
        value(x);
    }
    template <class T> void optional(const char *name, const T &x, bool available) {
        key(name);
        if (available)
            value(x);
        else
            out << "null";
    }
    void value(const Interval &x) {
        out << '{';
        member("lower", x.lower, true);
        member("upper", x.upper);
        out << '}';
    }
    void value(const Energy &x) {
        out << '{';
        member("surface_enthalpy_j_m2", x.surface_enthalpy_j_m2, true);
        member("atmospheric_energy_j_m2", x.atmospheric_energy_j_m2);
        out << '}';
    }
    void value(const StateBox &x) {
        out << '{';
        member("surface_enthalpy_j_m2", x.surface_enthalpy_j_m2, true);
        member("atmospheric_energy_j_m2", x.atmospheric_energy_j_m2);
        out << '}';
    }
    void value(const FluxBox &x) {
        out << '{';
        member("surface_net_w_m2", x.surface_net_w_m2, true);
        member("atmospheric_net_w_m2", x.atmospheric_net_w_m2);
        out << '}';
    }
#define FIELD(name) member(#name, x.name)
    void value(const Water &x) {
        out << '{';
        member("freezing_temperature_k", x.freezing_temperature_k, true);
        FIELD(solid_heat_capacity_j_kg_k);
        FIELD(liquid_heat_capacity_j_kg_k);
        FIELD(latent_heat_j_kg);
        out << '}';
    }
    void value(const Column &x) {
        out << '{';
        member("area_m2", x.area_m2, true);
        FIELD(dry_heat_capacity_j_m2_k);
        FIELD(atmospheric_heat_capacity_j_m2_k);
        FIELD(atmospheric_longwave_absorptivity);
        FIELD(sensible_exchange_w_m2_k);
        FIELD(surface_shortwave_albedo);
        out << '}';
    }
    void value(const t::Options &x) {
        out << '{';
        member("absolute_tolerance_w_m2", x.absolute_tolerance_w_m2, true);
        FIELD(relative_tolerance);
        FIELD(maximum_newton_iterations);
        FIELD(maximum_backtracks);
        out << '}';
    }
    void value(const WorkLimits &x) {
        out << '{';
        member("maximum_duration_trials", x.maximum_duration_trials, true);
        FIELD(maximum_air_iterations_per_trial);
        FIELD(maximum_stage_calls);
        FIELD(maximum_total_flux_evaluations);
        out << '}';
    }
    void value(const Budgets &x) {
        out << '{';
        member("maximum_numerical_equation_defect_j_m2", x.maximum_numerical_equation_defect_j_m2,
               true);
        FIELD(maximum_locator_width_seconds);
        FIELD(maximum_physical_time_error_seconds);
        FIELD(maximum_physical_event_state_error_j_m2);
        out << '}';
    }
    void value(Branch x) {
        switch (x) {
        case Branch::dry:
            value("dry");
            break;
        case Branch::solid:
            value("solid");
            break;
        case Branch::mixed:
            value("mixed");
            break;
        case Branch::liquid:
            value("liquid");
            break;
        }
    }
    void value(Goal x) {
        switch (x) {
        case Goal::within_branch: value("within_branch"); break;
        case Goal::next_phase_boundary: value("next_phase_boundary"); break;
        case Goal::fixed_duration: value("fixed_duration"); break;
        default: value("invalid"); break;
        }
    }
    void value(EndpointCertificate x) {
        switch (x) {
        case EndpointCertificate::direct_tube: value("direct_tube"); break;
        case EndpointCertificate::hermite_residual: value("hermite_residual"); break;
        default: value("invalid"); break;
        }
    }
    void value(const Input &x) {
        out << '{';
        member("segment_id", x.segment_id, true);
        FIELD(physical_boundary_id);
        FIELD(is_water);
        FIELD(is_lake);
        FIELD(water);
        FIELD(column);
        FIELD(water_mass_kg_m2);
        FIELD(incident_shortwave_w_m2);
        FIELD(initial);
        FIELD(start_seconds);
        FIELD(physical_boundary_seconds);
        FIELD(maximum_duration_seconds);
        FIELD(clock_quantum_seconds);
        FIELD(incoming_branch);
        FIELD(goal);
        FIELD(proposed_tube);
        FIELD(budgets);
        FIELD(limits);
        FIELD(stage_options);
        if (x.endpoint_certificate != EndpointCertificate::direct_tube || x.reconstruction_leaves != 0) {
            FIELD(endpoint_certificate);
            FIELD(reconstruction_leaves);
        }
        out << '}';
    }
    void value(const t::StageInput &x) {
        out << '{';
        member("stage_id", x.stage_id, true);
        FIELD(water);
        FIELD(column);
        FIELD(water_mass_kg_m2);
        FIELD(incident_shortwave_w_m2);
        FIELD(effective_duration_seconds);
        FIELD(reference);
        FIELD(guess);
        FIELD(options);
        out << '}';
    }
    void value(const Flux &x) {
        out << '{';
        key("surface", true);
        out << '{';
        member("temperature_k", x.surface.temperature_k, true);
        member("solid_mass_kg_m2", x.surface.solid_mass_kg_m2);
        member("liquid_mass_kg_m2", x.surface.liquid_mass_kg_m2);
        out << '}';
        FIELD(atmosphere_present);
        FIELD(atmospheric_temperature_k);
        FIELD(incident_shortwave_w_m2);
        FIELD(reflected_shortwave_w_m2);
        FIELD(absorbed_shortwave_w_m2);
        FIELD(surface_longwave_w_m2);
        FIELD(atmospheric_absorbed_longwave_w_m2);
        FIELD(atmospheric_upward_longwave_w_m2);
        FIELD(atmospheric_downward_longwave_w_m2);
        FIELD(sensible_surface_to_air_w_m2);
        FIELD(outgoing_longwave_w_m2);
        out << '}';
    }
    void stage(const t::Receipt &x, const std::string &stage_id) {
        out << '{';
        member("stage_id", stage_id, true);
        FIELD(accepted);
        FIELD(failure_code);
        FIELD(detail);
        FIELD(candidate_available);
        optional("candidate", x.candidate, x.candidate_available);
        optional("flux", x.flux, x.candidate_available);
        FIELD(surface_residual_w_m2);
        FIELD(atmospheric_residual_w_m2);
        FIELD(surface_solver_tolerance_w_m2);
        FIELD(atmospheric_solver_tolerance_w_m2);
        FIELD(surface_roundoff_allowance_j_m2);
        FIELD(atmospheric_roundoff_allowance_j_m2);
        FIELD(newton_iterations);
        FIELD(backtracks);
        FIELD(flux_evaluations);
        out << '}';
    }
    void value(const AirTrial &x) {
        out << '{';
        member("energy_j_m2", x.energy_j_m2, true);
        FIELD(evaluation_started);
        FIELD(flux_available);
        FIELD(equation_defect_available);
        FIELD(failure_code);
        optional("flux", x.flux, x.flux_available);
        optional("represented_equation_defect_j_m2", x.represented_equation_defect_j_m2,
                 x.equation_defect_available);
        out << '}';
    }
    void value(const DurationTrial &x) {
        out << '{';
        member("duration_seconds", x.duration_seconds, true);
        FIELD(first_stage_requested);
        FIELD(first_stage_called);
        FIELD(first_stage_in_incoming_branch);
        optional("first_stage_input", x.first_stage_input, x.first_stage_requested);
        key("first_stage");
        if (x.first_stage_called)
            stage(x.first_stage, x.first_stage_input.stage_id);
        else
            out << "null";
        FIELD(second_stage_used);
        FIELD(second_stage_called);
        optional("second_stage_input", x.second_stage_input, x.second_stage_used);
        key("second_stage");
        if (x.second_stage_called)
            stage(x.second_stage, x.second_stage_input.stage_id);
        else
            out << "null";
        key("air_trials");
        array(x.air_trials);
        FIELD(candidate_available);
        optional("endpoint", x.endpoint, x.candidate_available);
        optional("endpoint_flux", x.endpoint_flux, x.candidate_available);
        FIELD(represented_defects_available);
        optional("represented_surface_equation_defect_j_m2",
                 x.represented_surface_equation_defect_j_m2, x.represented_defects_available);
        optional("represented_air_equation_defect_j_m2", x.represented_air_equation_defect_j_m2,
                 x.represented_defects_available);
        FIELD(nominal_defects_available);
        optional("nominal_first_stage_defect", x.nominal_first_stage_defect,
                 x.nominal_defects_available);
        optional("nominal_endpoint_quadrature_defect", x.nominal_endpoint_quadrature_defect,
                 x.nominal_defects_available);
        optional("nominal_equation_l1_upper_j_m2", x.nominal_equation_l1_upper_j_m2,
                 x.nominal_defects_available);
        out << '}';
    }
    void guard(const GuardReceipt &x, bool fixed_duration) {
        out << '{';
        member("domain_proved", x.domain_proved, true);
        FIELD(finite_horizon_tube_proved);
        if (fixed_duration) { FIELD(fixed_time_endpoint_proved); }
        FIELD(transverse_monotonicity_proved);
        FIELD(first_physical_hit_proved);
        FIELD(no_physical_hit_proved);
        FIELD(tube);
        FIELD(field);
        FIELD(picard_image);
        FIELD(direction);
        FIELD(signed_surface_rate_w_m2);
        FIELD(original_boundary_j_m2);
        FIELD(represented_boundary_j_m2);
        FIELD(boundary_product_remainder_j_m2);
        FIELD(boundary_product_decomposition_exact);
        FIELD(boundary_representation_bridge_j_m2);
        optional("physical_first_hit_seconds", x.physical_first_hit_seconds,
                 x.first_physical_hit_proved);
        optional("physical_event_state", x.physical_event_state,
                 x.first_physical_hit_proved || x.no_physical_hit_proved || x.fixed_time_endpoint_proved);
        out << '}';
    }
    void value(const ComponentFluences &x) {
        out << '{';
        member("incident_shortwave_j", x.incident_shortwave_j, true);
        FIELD(reflected_shortwave_j);
        FIELD(absorbed_shortwave_j);
        FIELD(surface_longwave_j);
        FIELD(atmospheric_absorbed_longwave_j);
        FIELD(atmospheric_upward_longwave_j);
        FIELD(atmospheric_downward_longwave_j);
        FIELD(sensible_surface_to_air_j);
        FIELD(outgoing_longwave_j);
        FIELD(surface_storage_j);
        FIELD(air_storage_j);
        FIELD(surface_component_residual_j);
        FIELD(air_component_residual_j);
        FIELD(combined_component_residual_j);
        out << '}';
    }
    template <class T> void array(const std::vector<T> &xs) {
        out << '[';
        bool first = true;
        for (const auto &x : xs) {
            if (!first)
                out << ',';
            first = false;
            value(x);
        }
        out << ']';
    }
    void value(const ResidualLeaf &x) {
        out << '{';
        member("index", x.index, true);
        FIELD(polynomial);
        FIELD(trace_range);
        FIELD(surface_residual_integral_j_m2);
        FIELD(air_residual_integral_j_m2);
        out << '}';
    }
    void value(const ResidualCertificate &x) {
        out << '{';
        member("started", x.started, true);
        FIELD(available);
        FIELD(leaves_started);
        key("leaves"); array(x.leaves);
        optional("surface_residual_integral_j_m2", x.surface_residual_integral_j_m2, x.available);
        optional("air_residual_integral_j_m2", x.air_residual_integral_j_m2, x.available);
        optional("endpoint_l1_error_j_m2", x.endpoint_l1_error_j_m2, x.available);
        out << '}';
    }
    void value(const TubeProposalPass &x) {
        out << '{';
        member("proposed_tube", x.proposed_tube, true);
        FIELD(accepted); FIELD(failure_code);
        key("guard"); guard(x.guard, true);
        out << '}';
    }
    void value(const TubeProposalReceipt &x) {
        out << '{';
        member("schema", "terrestrial_automatic_tube_v1", true);
        member("maximum_passes", x.maximum_passes);
        FIELD(accepted); FIELD(failure_code); FIELD(detail);
        FIELD(input_available);
        optional("generated_input", x.generated_input, x.input_available);
        FIELD(passes_started);
        key("passes"); array(x.passes);
        out << '}';
    }
    void value(const Receipt &x) {
        out << '{';
        member("schema", x.request.endpoint_certificate != EndpointCertificate::direct_tube ||
                             x.request.reconstruction_leaves != 0
                             ? "terrestrial_phase_segment_receipt_v4"
                             : x.request.goal == Goal::fixed_duration
                             ? "terrestrial_phase_segment_receipt_v3"
                             : "terrestrial_phase_segment_receipt_v2", true);
        FIELD(accepted);
        FIELD(failure_code);
        FIELD(detail);
        FIELD(request);
        key("guard");
        guard(x.guard, x.request.goal == Goal::fixed_duration);
        key("trials");
        array(x.trials);
        FIELD(numerical_candidate_available);
        FIELD(selected_trial);
        FIELD(sampled_locator_available);
        optional("sampled_duration_locator_seconds", x.sampled_duration_locator_seconds,
                 x.sampled_locator_available);
        FIELD(selected_in_locator);
        FIELD(clock_quantum_seconds);
        FIELD(represented_gamma);
        FIELD(represented_second_weight);
        FIELD(nominal_gamma);
        optional("selected_duration_seconds", x.selected_duration_seconds,
                 x.numerical_candidate_available);
        optional("selected_end_seconds", x.selected_end_seconds, x.numerical_candidate_available);
        optional("remaining_duration_seconds", x.remaining_duration_seconds,
                 x.numerical_candidate_available);
        FIELD(quadrature_available);
        optional("quadrature", x.quadrature, x.quadrature_available);
        FIELD(physical_error_bounds_available);
        optional("physical_time_error_seconds", x.physical_time_error_seconds,
                 x.physical_error_bounds_available);
        optional("physical_event_state_error_j_m2", x.physical_event_state_error_j_m2,
                 x.physical_error_bounds_available);
        if (x.request.endpoint_certificate != EndpointCertificate::direct_tube ||
            x.request.reconstruction_leaves != 0) {
            FIELD(reconstruction);
            FIELD(direct_tube_error_available);
            optional("direct_tube_state_error_j_m2", x.direct_tube_state_error_j_m2,
                     x.direct_tube_error_available);
        }
        FIELD(selected_first_stage_in_incoming_branch);
        FIELD(numerical_budget_passed);
        FIELD(physical_budget_passed);
        FIELD(final_state_available);
        optional("final_state", x.final_state, x.final_state_available);
        FIELD(stage_calls_started);
        FIELD(duration_trials_started);
        FIELD(total_flux_evaluations);
        out << '}';
    }
#undef FIELD
};
} // namespace
std::string phase_segment_receipt_json(const Receipt &x) {
    Json json;
    json.value(x);
    return json.out.str();
}
std::string phase_segment_input_json(const Input &x) {
    Json json;
    json.value(x);
    return json.out.str();
}
std::string residual_certificate_json(const ResidualCertificate &x) {
    Json json;
    json.value(x);
    return json.out.str();
}
std::string tube_proposal_receipt_json(const TubeProposalReceipt &x) {
    Json json;
    json.value(x);
    return json.out.str();
}
} // namespace phase_segment_prototype
