"""Read-only, validated settlement-v3 inputs for dependent human estimates.

A water contribution is a known structural zero. A terrestrial zero outside
this model's annual support is unavailable. The older placement score keeps
its declared numeric sentinel; this boundary exposes the distinction to new
consumers. Geographic no-human baselines and legacy models have separate scopes.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any

from .settlement_climate_support import SEASONAL_SETTLEMENT_SELECTION_MODEL
from .settlement_routes import enrich_world_with_settlement_route_models


@dataclass(frozen=True)
class SettlementSiteInput:
    surface_applicable: bool
    available: bool
    value: float | None
    structural_zero: bool


def _exact(actual: Any, expected: Any) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(
            _exact(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _exact(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def _number(value: Any) -> float:
    if type(value) not in (int, float):
        raise ValueError("settlement source requires finite numbers")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError("settlement source requires finite numbers") from error
    if not math.isfinite(result):
        raise ValueError("settlement source requires finite numbers")
    return result


def require_settlement_v3_inputs(world: dict[str, Any]) -> dict[int, SettlementSiteInput]:
    """Validate the complete source before returning any consumable values.

    This does not mutate the world, generate new state, or certify climate physics.
    It independently replays retained annual support and placement. Exact
    metadata comparison additionally closes the historical validator's numeric
    coercions and extra-key acceptance for this new dependency boundary.
    """
    # Validator package imports include consumer dispatch; defer them until
    # the source modules have finished initialization.
    from .cli.validators.settlement import _validate_settlement_selection
    from .cli.validators.settlement_climate import replay_settlement_climate

    if type(world) is not dict or world.get("generation_scope") == "geo_only":
        raise ValueError("full settlement-v3 inputs required")
    model = world.get("settlement_selection_model")
    if type(model) is not dict or model.get("model_type") != SEASONAL_SETTLEMENT_SELECTION_MODEL:
        raise ValueError("exact settlement-v3 parent required")
    cells = world.get("cells")
    summary = world.get("summary")
    settlements = world.get("settlements")
    if type(cells) is not list or not cells or type(summary) is not dict or type(settlements) is not list:
        raise ValueError("complete settlement source collections required")
    precision = summary.get("output_float_precision")
    if type(precision) is not int or not 0 <= precision <= 8:
        raise ValueError("exact settlement source precision required")
    if type(summary.get("settlement_count")) is not int or summary["settlement_count"] != len(settlements):
        raise ValueError("typed complete selected-settlement count required")
    for settlement in settlements:
        if type(settlement) is not dict:
            raise ValueError("typed selected-settlement records required")
        for value in settlement.values():
            if type(value) in (int, float):
                _number(value)
    by_id: dict[int, dict[str, Any]] = {}
    for cell in cells:
        if type(cell) is not dict or type(cell.get("id")) is not int or cell["id"] < 0 or cell["id"] in by_id:
            raise ValueError("unique typed settlement cell ids required")
        by_id[cell["id"]] = cell
        for key in ("is_water", "is_lake", "is_river", "settlement_climate_supported"):
            if type(cell.get(key)) is not bool:
                raise ValueError("typed settlement source flags required")
        for key in ("settlement_score", "settlement_climate_temperature_c", "elevation_m",
                    "runoff_mm_y", "precipitation_mm_y", "ice_thickness_m", "lat_deg",
                    "boundary_convergent", "boundary_transform", "boundary_divergent",
                    "crust_age_ma", "sediment_thickness_m"):
            _number(cell.get(key))
        if not 0.0 <= cell["settlement_score"] <= 1.0:
            raise ValueError("settlement score outside its declared range")
        for key in ("lithology", "crust_type", "landform"):
            if type(cell.get(key)) is not str:
                raise ValueError("complete native settlement descriptors required")
        for key, count in (("position_3d", 3), ("temperature_monthly_c", 12), ("precipitation_monthly_mm", 12)):
            values = cell.get(key)
            if type(values) is not list or len(values) != count:
                raise ValueError("complete settlement source vectors required")
            for value in values:
                _number(value)
    for cell in cells:
        neighbors = cell.get("neighbors")
        if type(neighbors) is not list or any(type(value) is not int or value not in by_id for value in neighbors):
            raise ValueError("complete typed settlement neighbor links required")
        if len(neighbors) != len(set(neighbors)):
            raise ValueError("duplicate settlement neighbor link")
    try:
        selection, temperatures = replay_settlement_climate(world)
        if selection != SEASONAL_SETTLEMENT_SELECTION_MODEL or temperatures is None:
            raise ValueError("native settlement-v3 support required")
        # This existing annotator writes only model objects and summary keys.
        # Isolate those destinations; retain read-only cells and source records.
        annotated = dict(world)
        annotated["summary"] = dict(summary)
        enrich_world_with_settlement_route_models(annotated)
        if not _exact(model, annotated["settlement_selection_model"]):
            raise ValueError("settlement-v3 declaration differs from its exact contract")
        if _validate_settlement_selection(world, summary, by_id):
            raise ValueError("settlement-v3 independent selection replay failed")
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError("malformed settlement-v3 parent") from error
    result = {}
    for cell in cells:
        water = cell["is_water"] or cell["is_lake"]
        supported = cell["settlement_climate_supported"]
        score = _number(cell["settlement_score"])
        if (water or not supported) and score != 0.0:
            raise ValueError("structural or unsupported score must retain exact zero")
        available = water or supported
        result[cell["id"]] = SettlementSiteInput(
            surface_applicable=not water,
            available=available,
            value=score if available else None,
            structural_zero=water,
        )
    return result
