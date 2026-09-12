"""Public native-social boundaries with distinct structural and replay scopes.

Raw native output lacks the later Python own-model annotations. Its gate checks
published types, null/support pairs and available record coverage only. The full
world gate separately requires the independent annotated numerical validators.
"""
from __future__ import annotations
from typing import Any

from .native_social_availability import (
    NATIVE_SOCIAL_MODEL, ENVELOPE_KEYS, SUMMARY_AVAILABILITY_KEYS, NULLABLE_FIELDS,
    SOCIAL_MODEL_TYPES, exact_contract, finite_number, natural, indexed_records,
    _nullable_fields, uses_native_social_availability,
)

RECORDED_SUMMARY_FIELDS = frozenset({
    'native_social_summary_availability', 'recorded_historical_event_count',
    'recorded_ruin_count', 'recorded_conflict_count', 'recorded_dynasty_count',
    'available_population_region_count', 'available_culture_continuity_count',
})
NATIVE_SOCIAL_PUBLIC_MODELS = frozenset(SOCIAL_MODEL_TYPES) | {
    'native_social_availability_model', 'settlement_selection_model',
    'route_network_model', 'political_region_model', 'political_border_model',
    'trade_flow_model', 'language_region_model',
}


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError('native social publication: ' + message)


def _ids(value: Any, *, limit: int | None = None) -> list[int]:
    _require(type(value) is list and all(type(item) is int and item >= 0 for item in value), 'typed ID list required')
    _require(value == sorted(set(value)), 'sorted unique IDs required')
    if limit is not None:
        _require(all(item < limit for item in value), 'ID outside declared record coverage')
    return value


def require_raw_native_social_publication(
    world: Any, *, geography_only: bool, include_cells: bool, require_current: bool,
) -> None:
    """Read-only raw shape/coverage check; not a social numerical certificate."""
    _require(type(world) is dict and type(world.get('summary')) is dict, 'world/summary objects required')
    keys = ('native_social_availability_model', 'native_social_availability')
    present = any(key in world for key in keys)
    if geography_only:
        _require(not present, 'geography-only native output must not publish human inference')
        _require(not RECORDED_SUMMARY_FIELDS.intersection(world['summary']), 'geography-only social coverage is inapplicable')
        return
    if not present:
        _require(not require_current, 'current seasonal full output requires its native social envelope')
        uses_native_social_availability(world)  # Reject orphan successor fields.
        return
    _require(all(key in world for key in keys), 'partial native social envelope')
    _require(exact_contract(world[keys[0]], NATIVE_SOCIAL_MODEL), 'unknown exact native social model')
    summary = world['summary']
    total_cells = natural(summary.get('cell_count'))
    cells = world.get('cells')
    _require(type(cells) is list, 'cells array required')
    if include_cells:
        _require(len(cells) == total_cells and all(type(cell) is dict and type(cell.get('id')) is int and cell['id'] == i for i, cell in enumerate(cells)), 'complete canonical cell coverage required')
        for cell in cells:
            _require(type(cell.get('is_water')) is bool and type(cell.get('is_lake')) is bool, 'typed native surface selectors required')
            temperature = finite_number(cell.get('settlement_climate_temperature_c'))
            support = cell.get('settlement_climate_supported')
            _require(type(support) is bool and support == (-14 < temperature < 48), 'typed annual support disagrees with its exact retained input')
            score = finite_number(cell.get('settlement_score'))
            _require(0 <= score <= 1, 'settlement score out of range')
            _require(not (cell['is_water'] or cell['is_lake'] or not support) or score == 0, 'native structural/unavailable score must be zero')
    else:
        _require(cells == [], 'summary-only raw output must have cells=[]')
    flags = summary.get('native_social_summary_availability')
    _require(type(flags) is dict and flags.keys() == SUMMARY_AVAILABILITY_KEYS and all(type(value) is bool for value in flags.values()), 'complete typed summary availability required')
    for key, available in flags.items():
        _require(key in summary, 'missing declared summary estimate: ' + key)
        if not available:
            _require(summary[key] is None, 'unavailable summary estimate must be null: ' + key)
        elif key.endswith('_count') or key == 'max_dynasty_lineage_depth':
            natural(summary[key])
        else:
            finite_number(summary[key])
    envelope = world[keys[1]]
    _require(type(envelope) is dict and envelope.keys() == ENVELOPE_KEYS, 'exact coverage fields required')
    for key,value in envelope.items():
        if key.endswith('_available'):
            _require(type(value) is bool, 'typed family availability required')
        elif key.endswith('_count'):
            natural(value)
    for applicable,supported,missing,limit in (
        ('ruin_candidate_cell_count','ruin_supported_candidate_cell_count','ruin_unavailable_cell_ids',total_cells),
        ('dynasty_applicable_region_count','dynasty_available_region_count','dynasty_unavailable_region_ids',len(indexed_records(world,'political_regions'))),
    ):
        absent=_ids(envelope[missing],limit=limit)
        _require(envelope[supported]+len(absent)==envelope[applicable], 'inconsistent declared source counts: '+applicable)
    pairs=envelope['conflict_unavailable_region_pairs']
    region_count=len(world['political_regions'])
    _require(type(pairs) is list and all(type(pair) is list and len(pair)==2 and all(type(i) is int and 0<=i<region_count for i in pair) and pair[0]<pair[1] for pair in pairs), 'typed unavailable region pairs required')
    _require(pairs==[list(pair) for pair in sorted(set(tuple(pair) for pair in pairs))], 'unique sorted unavailable region pairs required')
    _require(envelope['conflict_supported_pair_count']+len(pairs)==envelope['conflict_candidate_pair_count'], 'inconsistent conflict source counts')
    for flag, applicable, supported in (
        ('ruin_inference_available','ruin_candidate_cell_count','ruin_supported_candidate_cell_count'),
        ('conflict_inference_available','conflict_candidate_pair_count','conflict_supported_pair_count'),
        ('dynasty_inference_available','dynasty_applicable_region_count','dynasty_available_region_count'),
    ):
        _require(envelope[flag] == (envelope[applicable] == envelope[supported]), 'family flag disagrees with declared coverage')
    for family,kind in (
        ('cultures','CultureRegion'), ('population_regions','PopulationRegion'),
        ('historical_eras','HistoricalEra'), ('historical_events','HistoricalEvent'),
        ('territorial_snapshots','TerritorialSnapshot'),
    ):
        for record in indexed_records(world,family):
            _nullable_fields(record,kind)
            if family=='population_regions':
                counts={key:natural(record.get(key)) for key in ('territory_cell_count','site_input_applicable_cell_count','site_input_supported_cell_count','structural_zero_site_cell_count')}
                _require(counts['site_input_supported_cell_count'] <= counts['site_input_applicable_cell_count'] <= counts['territory_cell_count'], 'population site count coverage mismatch')
                _require(counts['site_input_applicable_cell_count']+counts['structural_zero_site_cell_count'] <= counts['territory_cell_count'], 'population structural count exceeds territory')
                _require(type(record.get('site_input_complete')) is bool and record['site_input_complete'] == (counts['site_input_applicable_cell_count']==counts['site_input_supported_cell_count']), 'population site completeness mismatch')
                for field in ('territory_area_km2','site_input_applicable_area_km2','site_input_supported_area_km2','structural_zero_site_area_km2'):
                    _require(finite_number(record.get(field))>=0, 'nonnegative declared population area required')
                _require(record['site_strength_available']==record['capacity_estimate_available'] and (not record['capacity_estimate_available'] or record['site_input_complete']) and (not record['population_estimate_available'] or record['capacity_estimate_available']), 'population prerequisite flag mismatch')
                _require(record.get('estimate_scope_status') in {'complete','unavailable_inputs','not_applicable_no_positive_territory'}, 'unknown population estimate scope')
            if family=='territorial_snapshots':
                rows=record.get('regions')
                _require(type(rows) is list and all(type(row) is dict for row in rows),'snapshot region records required')
                for row in rows:
                    _nullable_fields(row,'SnapshotRegion')
                    for field in ('base_area_km2','base_dissolved_polygon_area_km2','base_boundary_perimeter_km'):
                        _require(finite_number(row.get(field))>=0,'nonnegative base geometry required')
    for family in ('ruins','conflicts','dynasties'):
        indexed_records(world,family)
    for family,field,flag in (
        ('ruins','recorded_ruin_count','ruin_inference_available'),
        ('conflicts','recorded_conflict_count','conflict_inference_available'),
        ('dynasties','recorded_dynasty_count','dynasty_inference_available'),
    ):
        _require(type(summary.get(field)) is int and summary[field]==len(world[family]),'recorded family count mismatch: '+family)
        if family!='dynasties' and not envelope[flag]:
            _require(not world[family], 'incomplete global selection cannot publish a selected subset')
    _require(type(summary.get('recorded_historical_event_count')) is int and summary['recorded_historical_event_count']==len(world['historical_events']),'recorded event count mismatch')
    for field,family,flag in (
        ('available_population_region_count','population_regions','population_estimate_available'),
        ('available_culture_continuity_count','cultures','continuity_estimate_available'),
    ):
        _require(type(summary.get(field)) is int and summary[field]==sum(row[flag] for row in world[family]),'available record count mismatch')
    event_types=['state_foundation','dynastic_change','migration','language_split','trade_boom','sacred_founding','ruin_abandonment']
    coverage=envelope['historical_event_family_coverage']
    _require(type(coverage) is list and len(coverage)==len(event_types),'complete event-family coverage required')
    for row,kind in zip(coverage,event_types):
        _require(type(row) is dict and row.keys()=={'event_type','inference_available','applicable_source_count','available_source_count','recorded_event_count'} and row['event_type']==kind and type(row['inference_available']) is bool,'typed exact event-family entry required')
        available=natural(row['available_source_count']);recorded=natural(row['recorded_event_count'])
        if row['applicable_source_count'] is not None:
            _require(available<=natural(row['applicable_source_count']),'available family count exceeds applicability')
        _require(recorded==sum(event.get('type')==kind for event in world['historical_events']),'event-family record coverage mismatch')
    _require(envelope['historical_event_inference_available']==all(row['inference_available'] for row in coverage),'historical envelope completeness mismatch')
    _require(envelope['territorial_snapshot_inference_available']==all(row['geometry_estimate_available'] and row['population_estimate_available'] for row in world['territorial_snapshots']),'snapshot envelope completeness mismatch')


def validate_public_native_social(world: Any) -> tuple[bool,list[str]]:
    """Full annotated world: independently audit all seven native social models."""
    try:
        current=uses_native_social_availability(world)
        if not current:
            return False,[]
        from .cultural_geography_validation import validate_cultural_geography_replay
        from .historical_geography_validation import validate_historical_geography_replay
        from .civilization_geography_validation import validate_civilization_geography_replay
        from .territorial_geography_validation import validate_territorial_geography_replay
        errors=[]
        for validate in (validate_cultural_geography_replay,validate_historical_geography_replay,validate_civilization_geography_replay,validate_territorial_geography_replay):
            errors.extend(validate(world))
        return True,errors[:12]
    except (ValueError,TypeError,KeyError,OverflowError,IndexError) as exc:
        return False,['native social publication: '+str(exc)[:500]]
