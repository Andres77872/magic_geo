#include "layered_ice_owner.hpp"

#include <bit>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <locale>
#include <sstream>

namespace magic_geo::detail {
namespace {

// Escape bytes independently, including invalid UTF-8. This is a deterministic
// and injective encoding of the identifiers used for exact request identity.
std::string quote(const std::string& value) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << '"';
    for (unsigned char c : value) {
        if (c == '"' || c == '\\') out << '\\' << c;
        else if (c < 32 || c > 126)
            out << "\\u00" << std::hex << std::setw(2) << std::setfill('0')
                << static_cast<unsigned int>(c);
        else out << c;
    }
    out << '"';
    return out.str();
}

std::string number(double value) {
    std::ostringstream out;
    out.imbue(std::locale::classic());
    const auto bits = std::bit_cast<std::uint64_t>(value);
    // Inspect the representation before any floating-point classification, so
    // rejected infinities and every NaN sign/payload retain their input bits.
    if ((bits & UINT64_C(0x7ff0000000000000)) == UINT64_C(0x7ff0000000000000))
        out << "{\"nonfinite_binary64_bits\":\"" << std::hex << std::setw(16)
            << std::setfill('0') << bits << "\"}";
    else out << std::setprecision(std::numeric_limits<double>::max_digits10) << value;
    return out.str();
}

struct Object {
    std::string value = "{";
    void add(const char* key, const std::string& encoded) {
        if (value.size() > 1) value += ',';
        value += quote(key) + ':' + encoded;
    }
    void num(const char* key, double x) { add(key, number(x)); }
    void flag(const char* key, bool x) { add(key, x ? "true" : "false"); }
    std::string finish() const { return value + '}'; }
};

template<class Range, class F>
std::string array(const Range& values, F encode) {
    std::string result = "[";
    for (const auto& value : values) {
        if (result.size() > 1) result += ',';
        result += encode(value);
    }
    return result + ']';
}

std::string interval(EnthalpyMeshInterval value) {
    Object out;
    out.num("lower", value.lower);
    out.num("upper", value.upper);
    return out.finish();
}

std::string address(LayeredMaterialAddress value) {
    Object out;
    out.add("cell_id", std::to_string(value.cell_id));
    out.add("layer_id", std::to_string(value.layer_id));
    return out.finish();
}

std::string movement(const LayeredMaterialMovement& value) {
    Object out;
    out.add("id", quote(value.id));
    out.add("donor", address(value.donor));
    out.add("recipient", address(value.recipient));
    out.add("phase", std::to_string(static_cast<int>(value.phase)));
    out.num("mass_kg", value.mass_kg);
    out.num("import_temperature_k", value.import_temperature_k);
    return out.finish();
}

std::string location(LayeredIceRemapLocation value) {
    Object out;
    out.flag("deep", value.deep);
    out.add("layer_id", std::to_string(value.layer_id));
    return out.finish();
}

template<class Plan>
std::string remap(const Plan& value) {
    Object out, limits;
    out.add("id", quote(value.id));
#define LIMIT(name) limits.add(#name, std::to_string(value.limits.name))
    LIMIT(max_columns);
    LIMIT(max_active_nodes);
    LIMIT(max_donors);
    LIMIT(max_allocations);
    LIMIT(max_arithmetic_groups);
    if constexpr(requires {value.limits.max_exports;}) LIMIT(max_exports);
#undef LIMIT
    out.add("limits", limits.finish());
    out.add("targets", array(value.targets, [](const auto& target) {
        Object column;
        column.add("cell_id", std::to_string(target.cell_id));
        column.add("layers", array(target.layers, [](const auto& layer) {
            Object out;
            out.add("layer_id", std::to_string(layer.layer_id));
            out.num("density_kg_m3", layer.density_kg_m3);
            out.num("conductivity_w_m_k", layer.conductivity_w_m_k);
            return out.finish();
        }));
        column.add("deep_density_kg_m3", target.deep_density_kg_m3
            ? number(*target.deep_density_kg_m3) : "null");
        return column.finish();
    }));
    out.add("donors", array(value.donors, [](const auto& donor) {
        Object out;
        out.add("cell_id", std::to_string(donor.cell_id));
        out.add("source", location(donor.source));
        out.add("allocations", array(donor.allocations, [](const auto& allocation) {
            Object out;
            out.add("destination", location(allocation.destination));
            out.add("weight", std::to_string(allocation.weight));
            return out.finish();
        }));
        return out.finish();
    }));
    if constexpr(requires {value.exports;}) {
        out.add("exports",array(value.exports,[](const auto& e) {
            Object out;out.add("id",quote(e.id));out.add("donor",address(e.donor));
            out.add("phase",std::to_string(static_cast<int>(e.phase)));return out.finish();
        }));
    }
    return out.finish();
}

std::string forcing(const LayeredIceOwnerForcing& value) {
    Object out;
    out.add("id", quote(value.id));
    out.num("begin_seconds", value.begin_seconds);
    out.num("end_seconds", value.end_seconds);
    out.add("absorbed_shortwave_w_m2", array(value.absorbed_shortwave_w_m2, number));
    return out.finish();
}

std::string thermal_options(const EnthalpyMeshOptions& value) {
    Object out;
    out.num("duration_seconds", value.duration_seconds);
    out.num("maximum_stage_error_j", value.maximum_stage_error_j);
    out.num("maximum_endpoint_error_j", value.maximum_endpoint_error_j);
    out.add("maximum_sweeps", std::to_string(value.maximum_sweeps));
    out.add("maximum_coordinate_iterations", std::to_string(value.maximum_coordinate_iterations));
    out.add("maximum_scalar_evaluations", std::to_string(value.maximum_scalar_evaluations));
    out.add("reconstruction_leaves", std::to_string(value.reconstruction_leaves));
    out.flag("allow_pure_water_columns", value.allow_pure_water_columns);
    return out.finish();
}

std::string owner_limits(const LayeredIceOwnerLimits& value) {
    Object out;
#define LIMIT(name) out.add(#name, std::to_string(value.name))
    LIMIT(max_prepare_attempts);
    LIMIT(max_commits);
    LIMIT(max_concurrent_preparations);
    LIMIT(max_events_per_transition);
    LIMIT(max_consumed_events);
    LIMIT(max_pending_outboxes);
    LIMIT(max_thermal_nodes);
    LIMIT(max_thermal_edges);
    LIMIT(max_node_leaves);
    LIMIT(max_receipt_bytes);
    LIMIT(max_history_bytes);
    LIMIT(max_stored_forcing_values);
    LIMIT(max_private_receipt_bytes);
    LIMIT(max_retained_preparations);
#undef LIMIT
    return out.finish();
}

std::string parcel(const LayeredMaterialParcelCertificate& value) {
    Object out;
    out.add("movement", movement(value.movement));
    out.num("donor_temperature_k", value.donor_temperature_k);
    out.num("specific_enthalpy_j_kg", value.specific_enthalpy_j_kg);
    out.num("carried_enthalpy_j", value.carried_enthalpy_j);
    out.add("ideal_specific_enthalpy_j_kg", interval(value.ideal_specific_enthalpy_j_kg));
    out.add("ideal_carried_enthalpy_j", interval(value.ideal_carried_enthalpy_j));
    out.add("energy_projection_j", interval(value.energy_projection_j));
    out.flag("external_outbox", value.external_outbox);
    return out.finish();
}

std::string owned_parcel(const LayeredIceOwnedParcel& value) {
    Object out;
    out.add("transaction_id", quote(value.transaction_id));
    out.add("source_revision", std::to_string(value.source_revision));
    out.add("parcel", parcel(value.parcel));
    out.add("geographic_cell_id", std::to_string(value.geographic_cell_id));
    return out.finish();
}

std::string domain(const LayeredIceOwnerDomainCoordinate& value) {
    Object out;
    out.add("address", address(value.address));
    out.add("enthalpy_box_j_m2", interval(value.enthalpy_box_j_m2));
    out.add("physical_floor_j_m2", interval(value.physical_floor_j_m2));
    return out.finish();
}

std::string thermal_ledger(const LayeredIceOwnerThermalLedger& value) {
    Object out;
#define INTERVAL(name) out.add(#name, interval(value.name))
    INTERVAL(storage_change_j);
    INTERVAL(weighted_shortwave_j);
    INTERVAL(weighted_emission_j);
    INTERVAL(physical_duration_shortwave_j);
    INTERVAL(shortwave_duration_bridge_j);
    INTERVAL(balance_residual_j);
    INTERVAL(assembled_defect_j);
#undef INTERVAL
    out.add("weighted_edge_transfer_j", array(value.weighted_edge_transfer_j, interval));
    out.add("first_field_conversion_defect_j_m2", array(value.first_field_conversion_defect_j_m2, interval));
    return out.finish();
}

std::string thermal_error_charge(const LayeredIceOwnerThermalErrorCharge& value) {
    Object out;
    out.num("before_global_energy_error_j", value.before_global_energy_error_j);
    out.num("local_endpoint_error_upper_j", value.local_endpoint_error_upper_j);
    out.num("after_global_energy_error_j", value.after_global_energy_error_j);
    out.add("charged_increment_j", interval(value.charged_increment_j));
    out.add("maximum_thermal_error_increment_j", value.maximum_thermal_error_increment_j
        ? number(*value.maximum_thermal_error_increment_j) : "null");
    out.flag("quota_passed", value.quota_passed);
    return out.finish();
}

} // namespace

std::string layered_ice_owned_parcel_json(const LayeredIceOwnedParcel& value) {
    return owned_parcel(value);
}
std::string layered_ice_absorption_selection_json(const LayeredIceAbsorptionSelection& value) {
    Object out;out.add("transaction_id",quote(value.transaction_id));out.add("event_id",quote(value.event_id));
    out.add("recipient",address(value.recipient));return out.finish();
}
std::string layered_ice_absorption_request_json(const LayeredIceAbsorptionRequest& value) {
    Object out;out.add("initial",layered_ice_input_json(value.initial));
    out.add("pending_outboxes",array(value.pending_outboxes,owned_parcel));
    out.add("selections",array(value.selections,layered_ice_absorption_selection_json));
    out.num("inherited_joint_energy_error_j",value.inherited_joint_energy_error_j);
    out.num("maximum_final_energy_error_j",value.maximum_final_energy_error_j);return out.finish();
}
std::string layered_ice_absorption_receipt_json(const LayeredIceAbsorptionReceipt& value) {
    Object out;out.add("model",quote("same_joint_owner_prescribed_whole_parcel_absorption_v1"));
    out.add("energy_error_scope",quote("canonical_projected_W_joint_retained_remaining_pending_L1_joules_v1"));
    for(const char* key:{"original_mass_trajectory_certified","source_history_authenticated","automatic_routing_policy",
                        "external_delivery_acknowledged","ordinary_generation_changed"}) out.flag(key,false);
    out.flag("accepted",value.accepted);out.add("failure_code",quote(value.failure_code));out.add("detail",quote(value.detail));
    out.add("request",value.request?layered_ice_absorption_request_json(*value.request):"null");
    out.add("source_graph",value.source_graph?layered_ice_graph_json(*value.source_graph):"null");
    out.add("nodes",array(value.nodes,[](const auto& n) {
        Object x;x.add("address",address(n.address));
#define NUMBER(k) x.num(#k,n.k)
        NUMBER(area_m2);NUMBER(nonwater_capacity_j_m2_k);NUMBER(initial_W);NUMBER(initial_H);NUMBER(final_W);NUMBER(final_H);
#undef NUMBER
#define INTERVAL(k) x.add(#k,interval(n.k))
        INTERVAL(absorbed_mass_kg);INTERVAL(absorbed_energy_j);INTERVAL(ideal_final_W);INTERVAL(ideal_final_H);
        INTERVAL(mass_projection_kg_m2);INTERVAL(energy_projection_j_m2);INTERVAL(before_H);INTERVAL(before_floor);
        INTERVAL(after_H);INTERVAL(after_floor);
#undef INTERVAL
        return x.finish();
    }));
    Object work;
#define COUNT(k) work.add(#k,std::to_string(value.work.k))
    COUNT(source_builder_calls_started);COUNT(output_builder_calls_started);COUNT(parcels_absorbed);COUNT(nodes_updated);
#undef COUNT
    out.add("work",work.finish());out.num("energy_projection_defect_upper_j",value.energy_projection_defect_upper_j);
#define INTERVAL(k) out.add(#k,interval(value.k))
    INTERVAL(absorbed_mass_kg);INTERVAL(absorbed_energy_j);INTERVAL(retained_mass_change_kg);INTERVAL(retained_energy_change_j);
    INTERVAL(mass_balance_residual_kg);INTERVAL(energy_balance_residual_j);
#undef INTERVAL
    if(value.final) {
        Object f;f.add("graph",layered_ice_graph_json(value.final->graph));
        f.add("pending_outboxes",array(value.final->pending_outboxes,owned_parcel));
        f.num("final_joint_energy_error_j",value.final->final_joint_energy_error_j);out.add("final",f.finish());
    } else out.add("final","null");
    return out.finish();
}

std::string layered_ice_owner_request_json(const LayeredIceOwnerRequest& value) {
    Object out;
    out.add("id", quote(value.id));
    out.add("expected_revision", std::to_string(value.expected_revision));
    out.num("end_seconds", value.end_seconds);
    out.add("movements", array(value.movements, movement));
    out.add("remap", value.remap ? remap(*value.remap) : "null");
    out.add("forcing", value.forcing ? forcing(*value.forcing) : "null");
    out.add("thermal", value.thermal ? thermal_options(*value.thermal) : "null");
    out.add("absorptions",array(value.absorptions,layered_ice_absorption_selection_json));
    out.add("topology",value.topology?remap(*value.topology):"null");
    out.add("maximum_thermal_error_increment_j", value.maximum_thermal_error_increment_j
        ? number(*value.maximum_thermal_error_increment_j) : "null");
    return out.finish();
}

namespace {
std::string snapshot_reference(const LayeredIceOwnerSnapshot& value) {
    Object out;
    out.add("owner_id",quote(value.owner_id));
    out.add("snapshot_revision",std::to_string(value.revision));
    return out.finish();
}

std::string snapshot_json(const LayeredIceOwnerSnapshot& value,
                          const LayeredIceOwnerSnapshot* prefix) {
    Object out;
    out.add("owner_id", quote(value.owner_id));
    out.add("revision", std::to_string(value.revision));
    out.num("elapsed_seconds", value.elapsed_seconds);
    out.num("joint_energy_error_j", value.joint_energy_error_j);
    out.add("graph", layered_ice_graph_json(value.graph));
    if(prefix) {
        if(value.owner_id!=prefix->owner_id ||
           &value.geographic_epoch.nodes()!=&prefix->geographic_epoch.nodes() ||
           value.geographic_cell_ids!=prefix->geographic_cell_ids ||
           !value.forcing_history.has_prefix(prefix->forcing_history) ||
           value.forcing_history.size()-prefix->forcing_history.size()>1)
            throw LayeredIceError("journal_reference_refusal","normalized snapshot does not extend its owned source");
        out.add("geographic_epoch_ref",snapshot_reference(*prefix));
        out.add("geographic_cell_ids_ref",snapshot_reference(*prefix));
    } else {
        out.add("geographic_epoch", seasonal_liquid_routing_graph_json(value.geographic_epoch));
        out.add("geographic_cell_ids", array(value.geographic_cell_ids, [](int id) {
            return std::to_string(id);
        }));
    }
    out.add("pending_outboxes", array(value.pending_outboxes, owned_parcel));
    out.add("consumed_event_ids", array(value.consumed_event_ids, quote));
    if(prefix) out.add("forcing_history_prefix_length",std::to_string(value.forcing_history.size()));
    else out.add("forcing_history", array(value.forcing_history, forcing));
    return out.finish();
}
} // namespace

std::string layered_ice_owner_snapshot_json(const LayeredIceOwnerSnapshot& value) {
    return snapshot_json(value,nullptr);
}

std::string layered_ice_owner_journal_seed_json(const LayeredIceOwnerSnapshot& value) {
    return snapshot_json(value,nullptr);
}

std::string layered_ice_owner_work_json(const LayeredIceOwnerWork& value) {
    Object out;
#define COUNT(name) out.add(#name, std::to_string(value.name))
    COUNT(prepare_attempts);
    COUNT(graph_builds_started);
    COUNT(material_calls_started);
    COUNT(calorimeter_calls_started);
    COUNT(remap_calls_started);
    COUNT(thermal_calls_started);
    COUNT(absorption_calls_started);
    COUNT(topology_calls_started);
    COUNT(internal_be_calls_started);
    COUNT(scalar_evaluations);
#undef COUNT
    out.flag("observed_counts_complete", value.observed_counts_complete);
    return out.finish();
}

namespace {
std::string receipt_json(const LayeredIceOwnerReceipt& value,bool normalized) {
    Object out;
    out.add("model", quote("mapped_atomic_layered_ice_owner_v5"));
    out.add("energy_error_scope", quote("canonical_projected_W_joint_active_deep_pending_outbox_L1_joules_v1"));
    out.flag("original_mass_trajectory_certified", false);
    out.flag("imported_source_accuracy_certified", false);
    out.flag("geometry_error_certified", false);
    out.flag("spatial_discretization_error_certified", false);
    out.flag("external_delivery_acknowledged", false);
    out.flag("ordinary_generation_changed", false);
    out.add("thermal_quota_scope", quote("actual_outward_joint_E_increment_after_sources_not_extra_error_charge_v1"));
    out.add("forcing_storage_scope", quote("immutable_shared_prefix_values_lossless_normalized_journal_v1"));
    out.add("retention_scope",quote("normalized_journal_and_private_record_wire_bytes_not_peak_resident_memory_v1"));
    out.flag("fixed_refusal_metadata_excluded_from_rich_retention_caps",true);
    out.flag("full_calendar_schedule_admitted", false);
    out.flag("prepared", value.prepared);
    out.add("failure_code", quote(value.failure_code));
    out.add("detail", quote(value.detail));
    out.add("limits", owner_limits(value.limits));
    out.num("maximum_joint_energy_error_j", value.maximum_joint_energy_error_j);
    out.add("request", value.request ? layered_ice_owner_request_json(*value.request) : "null");
    if(normalized && value.final && !value.initial)
        throw LayeredIceError("journal_reference_refusal","final snapshot has no referenced source");
    out.add("initial", value.initial ? (normalized ? snapshot_reference(*value.initial) :
        layered_ice_owner_snapshot_json(*value.initial)) : "null");
    out.add("final", value.final ? snapshot_json(*value.final,normalized?value.initial.get():nullptr) : "null");
    out.add("material", value.material ? layered_material_receipt_json(*value.material) : "null");
    out.add("remap", value.remap ? layered_ice_remap_receipt_json(*value.remap) : "null");
    out.add("thermal", value.thermal ? enthalpy_mesh_sdirk2_receipt_json(*value.thermal) : "null");
    out.add("thermal_ledger", value.thermal_ledger ? thermal_ledger(*value.thermal_ledger) : "null");
    out.add("thermal_error_charge", value.thermal_error_charge ? thermal_error_charge(*value.thermal_error_charge) : "null");
    out.add("absorption",value.absorption?layered_ice_absorption_receipt_json(*value.absorption):"null");
    out.add("topology",value.topology?layered_ice_topology_receipt_json(*value.topology):"null");
    out.add("initial_domain", array(value.initial_domain, domain));
    out.add("final_domain", array(value.final_domain, domain));
    out.add("work", layered_ice_owner_work_json(value.work));
    return out.finish();
}
} // namespace

std::string layered_ice_owner_receipt_json(const LayeredIceOwnerReceipt& value) {
    return receipt_json(value,false);
}

std::string layered_ice_owner_record_json(const LayeredIceOwnerReceipt& value,const std::string& replay_key) {
    Object out;
    out.add("record_model",quote("lossless_layered_owner_journal_record_v1"));
    out.add("replay_key",quote(replay_key));
    std::string appended="[]";
    if(value.initial && value.final) {
        if(value.initial->revision==std::numeric_limits<std::uint64_t>::max() ||
           value.final->revision!=value.initial->revision+1)
            throw LayeredIceError("journal_reference_refusal","final revision does not follow source");
        // snapshot_json independently verifies immutable prefix identity.
        if(value.final->forcing_history.size()==value.initial->forcing_history.size()+1)
            appended='['+forcing(value.final->forcing_history[value.initial->forcing_history.size()])+']';
    }
    out.add("appended_forcing",appended);
    out.add("receipt",receipt_json(value,true));
    return out.finish();
}

} // namespace magic_geo::detail
