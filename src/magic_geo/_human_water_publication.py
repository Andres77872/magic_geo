"""Atomic publication utility; equations are supplied by the owning producer."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

from .human_water_transport_validation import (
    HumanWaterTransportError,
    _DYNAMIC,
    _FAMILIES,
    _KEYS,
    _OWNED,
    owned_fields,
    validate_human_water_transport,
    validate_human_water_transport_inputs,
)


def publish_human_water_stage(
    world: dict[str, Any],
    stage: str,
    equations: Callable[[dict[str, Any]], dict[str, Any]],
    natural_model: dict[str, Any],
) -> dict[str, Any]:
    version = validate_human_water_transport_inputs(world, stage)
    states = None
    if version == 3:
        from .settlement_input_availability import require_settlement_v3_inputs
        try:
            states = require_settlement_v3_inputs(world)
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            raise HumanWaterTransportError('human water transport: invalid settlement source: ' + str(exc)[:450]) from exc
    staged = deepcopy(world)
    try:
        if version == 3:
            from . import _human_water_available_equations as available
            {'navigation': available.navigation, 'ports': available.ports, 'corridors': available.corridors}[stage](staged, states)
        else:
            equations(staged)
        if version == 2:
            key = _KEYS[stage]
            # Recomputed outputs and counts, not a retagged stale certificate.
            staged[key] = {**natural_model, **{k: staged[key][k] for k in _DYNAMIC[stage]}}
            staged['summary'][key] = natural_model['model_type']
        errors = validate_human_water_transport(staged, stage)
        if errors:
            raise HumanWaterTransportError(errors[0])
    except (ValueError, TypeError, KeyError, OverflowError, ArithmeticError) as exc:
        raise HumanWaterTransportError('human water transport: unpublished ' + stage + ' failed: ' + str(exc)[:450]) from exc
    # Every mutation below is a plain-dict update from fully prepared output.
    # Keep all parent/native objects and each caller cell/route dictionary intact.
    ownership = owned_fields(stage, version)
    for original, result in zip(world['cells'], staged['cells']):
        original.update({key: result[key] for key in ownership['cell']})
    if ownership['route']:
        for original, result in zip(world['routes'], staged['routes']):
            original.update({key: result[key] for key in ownership['route']})
    world.setdefault('summary', {}).update({key: staged['summary'][key] for key in ownership['summary']})
    world[_KEYS[stage]] = staged[_KEYS[stage]]
    world[_FAMILIES[stage]] = staged[_FAMILIES[stage]]
    return world
