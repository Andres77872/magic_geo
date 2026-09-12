"""Independent ore-v3 resource viability attachment and exact ancestry guards.

Physical ore equations are unchanged and remain owned by their existing replay.
This audit reconstructs the changed economic attachment and selected source links.
"""
from __future__ import annotations
import math
from typing import Any
from .resource_access_validation import DEPOSIT, exact, require

MODEL = 'causal_tectonic_lithologic_ore_genesis_diagnostics_v3'
LEGACY_MODEL = 'causal_tectonic_lithologic_ore_genesis_diagnostics_v2'
BASE = {'model_type':LEGACY_MODEL,'flow_accumulation_normalization_model':'positive_cell_p95_v1',
        'flow_accumulation_units':'runoff_mm_y_times_upstream_area_km2','physical_time_resolved':False,
        'model_limitation':'diagnostic metallogenic potential without reactive geochemical transport'}
POLICY = {**BASE, 'model_type':MODEL,'source_resource_deposit_model':DEPOSIT,
          'resource_viability_policy':'complete_selected_deposit_mean_or_null_with_coverage_and_separate_geographic_baseline',
          'physical_ore_policy':'unchanged_components_selection_confidence_and_material_links'}
CELL_FIELDS = ('ore_genesis_potential_index','hydrothermal_alteration_index','metallogenic_fertility_index','ore_structural_control_index','placer_concentration_index','ore_genesis_system_id')
SUMMARY_FIELDS = ('ore_genesis_system_count','ore_genesis_cell_count','ore_resource_deposit_count','high_ore_genesis_potential_cell_count','high_hydrothermal_alteration_cell_count','high_metallogenic_fertility_cell_count','high_placer_concentration_cell_count','ore_genesis_total_area_km2','mean_ore_genesis_potential_index','mean_hydrothermal_alteration_index','mean_metallogenic_fertility_index','mean_ore_structural_control_index','mean_placer_concentration_index','ore_genesis_system_type_counts')
TOP_FIELDS = ('ore_genesis_model','ore_genesis_systems')
ORE = {'volcanic_arc_metals','craton_iron_gold','placer_metals','geothermal'}

def version(world: dict[str,Any]) -> int:
    model=world.get('ore_genesis_model'); new_parent=isinstance(world.get('resource_deposit_model'),dict) and world['resource_deposit_model'].get('model_type')==DEPOSIT
    if 'ore_genesis_model' in world:
        require(type(model) is dict,'ore model must be an object')
        body={k:v for k,v in model.items() if k!='flow_accumulation_scale'}
        v=3 if exact(body,POLICY) else 2 if exact(body,BASE) else None
        require(v is not None,'unknown or malformed ore model')
        require(type(model.get('flow_accumulation_scale')) is float and math.isfinite(model['flow_accumulation_scale']) and model['flow_accumulation_scale']>=1,'ore normalization required')
        require((v==3)==new_parent,'ore own model requires exact resource parent; explicit upgrade required')
        if v == 2:
            require(not any(isinstance(r,dict) and any(k in r for k in ('mean_resource_viability_supported','resource_viability_applicable_deposit_count','resource_viability_supported_deposit_count','mean_geographic_resource_viability_baseline_index')) for r in world.get('ore_genesis_systems',[])), 'ore availability mirrors require v3')
        return v
    if new_parent:
        require(not any(k in world for k in TOP_FIELDS) and not any(k in world.get('summary',{}) for k in SUMMARY_FIELDS) and not any(any(k in c for k in CELL_FIELDS) for c in world['cells']), 'undeclared ore mirrors require explicit audited clearing')
        return 3
    return 2

def finite(value: Any) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except (ValueError, OverflowError):
        return False


def require_physical_sources(world: dict[str,Any]) -> None:
    cells = world["cells"]; by_id = {c["id"]: c for c in cells}
    for cell in cells:
        for key in ("resource","lithology","landform","crust_type","boundary_type"):
            require(type(cell.get(key)) is str, "ore explicit categorical source " + key + " required")
        for key in ("boundary_convergent","boundary_divergent","boundary_transform","tectonic_zone_strength","volcanic_potential_index","fault_slip_rate_index","seismic_hazard_index","crust_age_ma","crust_thickness_km","sediment_thickness_m","flow_accumulation","elevation_m","filled_elevation_m","area_km2","lat_deg","lon_deg"):
            require(finite(cell.get(key)), "ore explicit finite source " + key + " required")
        require(type(cell.get("is_river")) is bool,"ore explicit river flag required")
        for key in ("plate_id","collision_zone_id","subduction_zone_id","rift_zone_id","fault_system_id"):
            require(type(cell.get(key)) is int,"ore explicit source link " + key + " required")
        neighbors=cell.get("neighbors")
        require(type(neighbors) is list and all(type(n) is int and n in by_id and n != cell["id"] for n in neighbors) and len(neighbors)==len(set(neighbors)),"ore explicit unique known neighbor links required")
    for c in cells:
        require(all(c["id"] in by_id[n]["neighbors"] for n in c["neighbors"]),"ore reciprocal neighbor links required")

def validate_ore_resource_availability(world: dict[str,Any]) -> list[str]:
    try:
        require(version(world)==3 and 'ore_genesis_model' in world,'complete ore-v3 outputs required')
        from .biological_resource_validation import audit_biological_resource_deposits
        audit_biological_resource_deposits(world)
        require_physical_sources(world)
        records=world.get('ore_genesis_systems'); require(type(records) is list,'ore system list required')
        deposits={d['id']:d for d in world['resource_deposits']}; cells={c['id']:c for c in world['cells']}
        positive=sorted(max(0.0,float(c['flow_accumulation'])) for c in cells.values() if float(c['flow_accumulation'])>0)
        scale=max(1.0,positive[int(.95*(len(positive)-1))]) if positive else 1.0
        require(exact(world['ore_genesis_model'],{**POLICY,'flow_accumulation_scale':round(scale,6)}),'ore metadata or normalization mismatch')
        def finite_outputs(value):
            if type(value) in (int, float):
                require(finite(value), "nonfinite owned ore output")
            elif isinstance(value, dict):
                for item in value.values(): finite_outputs(item)
            elif isinstance(value, list):
                for item in value: finite_outputs(item)
        finite_outputs(records)
        for cell in world["cells"]:
            for key in CELL_FIELDS:
                require(key in cell and finite(cell[key]), "missing/nonfinite owned ore cell field " + key)
        for key in SUMMARY_FIELDS:
            require(key in world["summary"], "missing owned ore summary " + key)
            finite_outputs(world["summary"][key])
        for index,record in enumerate(records):
            require(type(record) is dict and type(record.get('id')) is int and record['id']==index,'ore dense IDs required')
            members=record.get('cell_ids'); require(type(members) is list and all(type(i) is int and i in cells for i in members) and len(set(members))==len(members),'ore member source links invalid')
            selected=[d for cid in members for d in world['resource_deposits'] if d['cell_id']==cid and d['resource'] in ORE]
            require(exact(record.get('resource_deposit_ids'),[d['id'] for d in selected]),'ore resource source IDs/order mismatch')
            require(exact(record.get('resource_deposit_count'),len(selected)),'ore resource count mismatch')
            count=sum(d['economic_viability_supported'] for d in selected); complete=count==len(selected)
            value=round(sum(d['economic_viability_index'] for d in selected)/len(selected),6) if selected and complete else (0.0 if not selected else None)
            baseline=round(sum(d['geographic_economic_viability_baseline_index'] for d in selected)/len(selected),6) if selected else 0.0
            expected={'mean_resource_viability_index':value,'mean_resource_viability_supported':complete,
                      'resource_viability_applicable_deposit_count':len(selected),'resource_viability_supported_deposit_count':count,
                      'mean_geographic_resource_viability_baseline_index':baseline}
            for k,v in expected.items():require(k in record and exact(record[k],v),'ore attachment '+k+' mismatch')
        return []
    except (ValueError,TypeError,KeyError,ArithmeticError) as exc:return ['ore resource availability: '+str(exc)]
