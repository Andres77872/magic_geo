"""Independent resource-v5 economic availability and raw numerical replay.

No producer functions/constants are imported. Geographic baselines are the old
S-absent diagnostic, not complete economic access. Native score sentinels remain
owned by settlement-v3; this module consumes the audited tri-state boundary.
"""
from __future__ import annotations
import math
from typing import Any

SETTLEMENT = 'causal_native_score_local_max_separated_settlement_selection_v3'
DEPOSIT = 'causal_geologic_resource_deposit_diagnostics_v5'
COMMODITY = 'causal_resource_commodity_occurrences_with_parent_support_v3'
ACCESS_SUMMARY_FIELDS = (
    'resource_accessibility_supported_deposit_count', 'unsupported_resource_accessibility_deposit_count',
    'resource_economic_viability_supported_deposit_count', 'unsupported_resource_economic_viability_deposit_count',
    'mean_resource_economic_viability_supported', 'high_viability_resource_deposit_count_complete',
    'mean_geographic_resource_viability_baseline_index',
)
RECORD_FIELDS = ('accessibility_supported', 'economic_viability_supported',
                 'geographic_accessibility_baseline_index', 'geographic_economic_viability_baseline_index')

def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError('resource access availability: ' + message)

def exact(a: Any, b: Any) -> bool:
    if type(a) is not type(b): return False
    if isinstance(b, dict): return a.keys() == b.keys() and all(exact(a[k], v) for k, v in b.items())
    if isinstance(b, list): return len(a) == len(b) and all(exact(x,y) for x,y in zip(a,b))
    return a == b

def is_new_source(world: dict[str, Any]) -> bool:
    model = world.get('settlement_selection_model')
    return world.get('generation_scope') == 'geo_only' or (isinstance(model,dict) and model.get('model_type') == SETTLEMENT) or any(isinstance(c,dict) and any(k in c for k in ('settlement_climate_supported','settlement_climate_temperature_c')) for c in world.get('cells',[]))

def access_policy(world: dict[str, Any]) -> dict[str, Any]:
    require('generation_scope' not in world or world['generation_scope'] in ('full_world','geo_only'), 'unknown generation scope')
    geo = world.get('generation_scope') == 'geo_only'
    return {
        'source_settlement_model': None if geo else SETTLEMENT,
        'economic_access_scope': 'geo_only_full_economic_estimate_unavailable' if geo else 'audited_settlement_v3_full_world',
        'economic_unavailable_policy': 'null_with_typed_support_preserve_material_records',
        'geographic_baseline_policy': 'unchanged_access_and_viability_equations_with_settlement_term_absent_not_full_economic_estimate',
        'economic_summary_policy': 'complete_record_means_or_null_supported_only_high_count_with_explicit_coverage',
        'water_settlement_policy': 'audited_water_contribution_structural_zero_not_terrestrial_unavailable',
    }

def source_inputs(world: dict[str, Any]):
    if world.get('generation_scope') == 'geo_only':
        require('settlement_selection_model' not in world and 'settlements' not in world,
                'geo scope must omit settlement declarations and records')
        require(all(not any(k in c for k in ('settlement_score','settlement_climate_supported','settlement_climate_temperature_c')) for c in world['cells']),
                'geo scope must omit settlement score and support mirrors')
        return None
    from .settlement_input_availability import require_settlement_v3_inputs
    return require_settlement_v3_inputs(world)

def clamp(v): return max(0.0, min(1.0, v))

def replay(cell: dict[str, Any], scale: float, site: Any, *, geo: bool) -> dict[str, Any]:
    """Retain binary64 operation ordering before six-place serialization."""
    g=lambda k: float(cell[k])
    resource=cell['resource']; land=cell['landform']; crust=cell['crust_type']
    convergent=clamp(g('boundary_convergent')); divergent=clamp(g('boundary_divergent'))
    sediment=clamp(g('sediment_thickness_m')/3.0); age=clamp(g('crust_age_ma')/2500.0)
    fertile=clamp(g('fertility')); salinity=clamp(g('soil_salinity_index')); runoff=clamp(g('runoff_mm_y')/900.0)
    flow=clamp(g('flow_accumulation')/max(1.0,scale))
    reserve=clamp({
        'volcanic_arc_metals': .34+convergent*.42+(.18 if land=='volcanic_arc' else 0.0),
        'craton_iron_gold': .28+age*.46+(.20 if crust=='craton' else 0.0),
        'sedimentary_fuels': .26+sediment*.48+(.12 if 'basin' in land else 0.0),
        'evaporites': .30+salinity*.36+(.24 if land=='salt_flat' else 0.0),
        'placer_metals': .24+flow*.34+convergent*.20+sediment*.14,
        'geothermal': .26+divergent*.34+convergent*.20+(.18 if land in {'volcanic_arc','rift_valley'} else 0.0),
        'fertile_alluvium': .24+fertile*.42+runoff*.16+(.16 if land in {'floodplain','delta'} else 0.0),
        'coastal_fisheries': .30+(.26 if cell['water_body_type']=='continental_shelf' else 0.0)+runoff*.12,
    }.get(resource,.18))
    evidence=.18
    if resource=='volcanic_arc_metals': evidence+=convergent*.36; evidence+=.22 if land=='volcanic_arc' else 0.0
    elif resource=='craton_iron_gold': evidence+=age*.34; evidence+=.24 if crust=='craton' else 0.0
    elif resource=='sedimentary_fuels': evidence+=sediment*.38; evidence+=.18 if 'basin' in land else 0.0
    elif resource=='evaporites': evidence+=salinity*.32; evidence+=.22 if land=='salt_flat' else 0.0
    elif resource=='placer_metals': evidence+=.22 if cell['is_river'] else 0.0; evidence+=flow*.26
    elif resource=='geothermal': evidence+=clamp(max(g('boundary_divergent'),g('boundary_convergent')))*.34; evidence+=.18 if land in {'volcanic_arc','rift_valley'} else 0.0
    elif resource=='fertile_alluvium': evidence+=fertile*.32; evidence+=.20 if land in {'floodplain','delta'} else 0.0
    elif resource=='coastal_fisheries': evidence+=.32 if cell['water_body_type']=='continental_shelf' else 0.0; evidence+=runoff*.12
    confidence=clamp(evidence*.72+reserve*.28)
    hazard=clamp(clamp(g('boundary_convergent')*.42+g('boundary_transform')*.30)+clamp(abs(g('elevation_m'))/3600.0)*.20+clamp(g('ice_thickness_m')/1600.0)*.20+clamp(g('seasonal_aridity_index'))*.10+salinity*.08)
    renew=.78 if resource in {'fertile_alluvium','coastal_fisheries'} else (.32 if resource=='geothermal' else .02)
    water=.20 if cell['is_river'] or cell['water_body_type'] in {'continental_shelf','fresh_lake'} else 0.0
    relief=clamp(abs(g('elevation_m'))/3000.0)
    geographic=clamp(.28+0.0*.42+water-relief*.20)
    viability=lambda a: clamp(reserve*.46+a*.30+confidence*.20-hazard*.18+renew*.10)
    available=bool(not geo and site.available)
    access=clamp(.28+clamp(site.value)*.42+water-relief*.20) if available else None
    return {'reserve_potential_index':reserve,'geologic_confidence_index':confidence,'extraction_hazard_index':hazard,'renewability_index':renew,
            'accessibility_index':access,'economic_viability_index':viability(access) if available else None,
            'accessibility_supported':available,'economic_viability_supported':available,
            'geographic_accessibility_baseline_index':geographic,'geographic_economic_viability_baseline_index':viability(geographic)}

def audit(world: dict[str, Any], records: list[dict[str,Any]], scale: float) -> list[dict[str, Any]]:
    sites=source_inputs(world); by_id={c['id']:c for c in world['cells']}; values=[]
    for record in records:
        cid=record['cell_id']; expected=replay(by_id[cid],scale,None if sites is None else sites[cid],geo=sites is None)
        for key,value in expected.items():
            serialized=round(value,6) if type(value) is float else value
            require(key in record and exact(record[key],serialized),f'deposit {record["id"]}: {key} raw replay mismatch')
        values.append(expected)
    n=len(values); count=sum(v['economic_viability_supported'] for v in values); complete=count==n
    expected_summary={
        'resource_accessibility_supported_deposit_count':count,'unsupported_resource_accessibility_deposit_count':n-count,
        'resource_economic_viability_supported_deposit_count':count,'unsupported_resource_economic_viability_deposit_count':n-count,
        'mean_resource_economic_viability_supported':complete,'high_viability_resource_deposit_count_complete':complete,
        'mean_resource_economic_viability_index':round(sum(v['economic_viability_index'] for v in values)/n,6) if n and complete else (0.0 if not n else None),
        'high_viability_resource_deposit_count':sum(v['economic_viability_supported'] and v['economic_viability_index']>=.65 for v in values),
        'mean_geographic_resource_viability_baseline_index':round(sum(v['geographic_economic_viability_baseline_index'] for v in values)/n,6) if n else 0.0,
    }
    for key,value in expected_summary.items():require(key in world['summary'] and exact(world['summary'][key],value),'summary '+key+' mismatch')
    return values
