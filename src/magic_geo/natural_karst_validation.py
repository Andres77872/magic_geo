"""Independent carbonate/soil/aquifer diagnostic replay, with exact ancestry."""
from __future__ import annotations

from collections import Counter
from typing import Any

from .natural_channel_validation import (
    _declaration, _finite, _output_same, _require,
    validate_natural_downstream_inputs,
)


def _bounded(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    _require(_finite(value), 'karst intermediate is unrepresentable')
    return max(lower, min(upper, value))


def _primary(values: list[str], fallback: str) -> str:
    counts = Counter(values)
    return min(counts, key=lambda value: (-counts[value], value)) if counts else fallback


def _expected(world: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    cells = world['cells']
    by_id = {c['id']: c for c in cells}
    outputs = {}
    candidates = set()
    totals = [0.0, 0.0, 0.0]
    limestone_count = 0
    limestone_karst_count = 0
    for cell in cells:
        cid = cell['id']
        marine = cell.get('water_body_type', 'land') in {'ocean','continental_shelf','inland_sea'}
        karst = cave = underground = 0.0
        if not bool(cell.get('is_water', False)) and not marine:
            lithology = str(cell.get('lithology', 'unknown'))
            soil_ph = float(cell.get('soil_ph', 7))
            carbonate = _bounded({'limestone':1.0,'sandstone':.18,'shale':.12,'metamorphic':.08,'volcanic':.04,'basalt':.03,'granite':.02}.get(lithology, .04)
                + _bounded((7.8 - soil_ph) / 3) * .12)
            moisture = _bounded(float(cell.get('soil_moisture_index', 0)))
            drainage = _bounded(float(cell.get('soil_drainage_index', 0)))
            profile = _bounded(float(cell.get('soil_profile_development_index', 0)))
            storage = _bounded(float(cell.get('aquifer_storage_index', 0)))
            productivity = _bounded(float(cell.get('aquifer_productivity_index', 0)))
            relief = _bounded(max((abs(float(cell.get('elevation_m', 0)) - float(by_id[n].get('elevation_m', 0))) for n in cell.get('neighbors', []) if n in by_id), default=0.0) / 1800)
            water = _bounded(_bounded(max(0.0, float(cell.get('precipitation_mm_y', 0))) / 1800) * .38
                + _bounded(max(0.0, float(cell.get('runoff_mm_y', 0))) / 900) * .18
                + _bounded(max(0.0, float(cell.get('groundwater_recharge_mm_y', 0))) / 520) * .28 + moisture * .16)
            temperature = _bounded((float(cell.get('temperature_c', 0)) + 6) / 24, .18, 1)
            aridity = _bounded(float(cell.get('seasonal_aridity_index', 0)))
            ice = _bounded(float(cell.get('ice_thickness_m', 0)) / 800)
            karst = _bounded(carbonate * (.22 + water * .36 + relief * .16 + drainage * .12 + profile * .10 + storage * .04) * temperature - aridity * .06 - ice * .20)
            cave = _bounded(karst * (.34 + relief * .30 + storage * .22 + profile * .14))
            underground = _bounded(karst * (.28 + productivity * .32 + drainage * .22 + relief * .18))
        values = karst, cave, underground
        for i, value in enumerate(values):
            totals[i] += value
        limestone = cell.get('lithology') == 'limestone' and not bool(cell.get('is_water', False))
        limestone_count += int(limestone)
        if karst >= .45:
            candidates.add(cid)
            limestone_karst_count += int(limestone)
        outputs[cid] = dict(zip(('karst_potential_index','cave_development_index','subterranean_drainage_fraction'), (round(v,6) for v in values)))
        outputs[cid]['karst_system_id'] = -1
    remaining = set(candidates)
    groups = []
    while remaining:
        start = min(remaining)
        remaining.remove(start)
        queue = [start]
        for cid in queue:
            for neighbor in by_id[cid].get('neighbors', []):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        groups.append(sorted(queue))
    records = []
    for sid, ids in enumerate(groups):
        members = [by_id[cid] for cid in ids]
        for cid in ids:
            outputs[cid]['karst_system_id'] = sid
        record = {'id':sid,'cell_count':len(ids),'cell_ids':ids,
            'area_km2':round(sum(max(0.0,float(c.get('area_km2',0))) for c in members),6),
            'dominant_lithology':_primary([str(c.get('lithology','unknown')) for c in members],'unknown'),
            'primary_aquifer_class':_primary([str(c.get('aquifer_class','unknown')) for c in members],'unknown'),
            'aquifer_system_ids':sorted({int(c.get('aquifer_system_id',-1)) for c in members if int(c.get('aquifer_system_id',-1)) >= 0}),
            'limestone_cell_fraction':round(sum(c.get('lithology') == 'limestone' for c in members)/len(ids),6)}
        for key in ('karst_potential_index','cave_development_index','subterranean_drainage_fraction'):
            record['mean_'+key] = round(sum(outputs[cid][key] for cid in ids)/len(ids),6)
        records.append(record)
    summary = {'karst_cell_count':len(candidates),'karst_system_count':len(records),
        'limestone_karst_cell_fraction':round(limestone_karst_count/limestone_count,6) if limestone_count else 0.0}
    for key, total in zip(('karst_potential_index','cave_development_index','subterranean_drainage_fraction'),totals):
        summary['mean_'+key] = round(total/max(1,len(cells)),6)
    return outputs, records, summary


def validate_natural_karst_diagnostics(world: Any) -> list[str]:
    """Bounded error list; no producer, CLI or test-data imports."""
    try:
        version = validate_natural_downstream_inputs(world, 'karst')
        declaration = _declaration(world, 'karst')
        _require(declaration == 2 if version == 2 else declaration is None, 'karst published identity mismatch')
        outputs, records, summary = _expected(world)
        for cell in world['cells']:
            for key, expected in outputs[cell['id']].items():
                _require(_output_same(cell.get(key), expected), f"cell {cell['id']}: {key} source replay mismatch")
        _require(_output_same(world.get('karst_systems'), records), 'karst systems source/component replay mismatch')
        for key, value in summary.items():
            _require(_output_same(world.get('summary',{}).get(key), value), 'summary.' + key + ' source replay mismatch')
        if version == 2:
            model = world['karst_diagnostics_model']
            _require(model['candidate_cell_count'] == summary['karst_cell_count'], 'karst candidate count mismatch')
            _require(model['system_count'] == len(records), 'karst system count mismatch')
        return []
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError) as exc:
        if isinstance(exc, ValueError):
            return [str(exc)[:600] or 'natural karst: invalid source or output']
        return ['natural karst: malformed input or output (' + type(exc).__name__ + ')']
