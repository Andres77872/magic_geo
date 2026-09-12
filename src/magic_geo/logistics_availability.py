"""Logistics equations with explicit nullable social inputs.

Native route geometry remains an independent source. This module never replaces
an unavailable economy or conflict input with a numerical fallback.
"""
from __future__ import annotations

from typing import Any, Callable

from .native_social_availability import finite_number


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _calculate(equation: Callable[..., float], *values: float | None) -> float | None:
    if any(value is None for value in values):
        return None
    return equation(*values)


def _estimate(record: dict[str, Any], key: str) -> float | None:
    flags = record.get("estimate_availability")
    if type(flags) is not dict or type(flags.get(key)) is not bool or key not in record:
        raise ValueError("declared economy estimate required: " + key)
    if not flags[key]:
        if record[key] is not None:
            raise ValueError("unavailable economy estimate must be null: " + key)
        return None
    return finite_number(record[key])


def _record(identity: dict[str, Any], estimates: dict[str, float | None]) -> dict[str, Any]:
    return {
        **identity,
        **{key: None if value is None else round(value, 6) for key, value in estimates.items()},
        "estimate_availability": {key: value is not None for key, value in estimates.items()},
    }


def _aggregate(rows: list[dict[str, Any]], key: str, *, mean: bool = False) -> float | None:
    values = [row[key] for row in rows]
    if any(value is None for value in values):
        return None
    # A complete, empty emitted family has a conditional zero statistic. Its
    # collection coverage is published separately; zero never certifies it.
    return round(sum(values) / max(1, len(values)) if mean else sum(values), 6)


def _conflict_pressure(world: dict[str, Any]) -> dict[int, float | None]:
    complete = world["native_social_availability"]["conflict_inference_available"]
    border_regions = {border[key] for border in world["borders"] for key in ("region_a", "region_b")}
    result = {
        region["id"]: 0.0 if complete or region["id"] not in border_regions else None
        for region in world["political_regions"]
    }
    for conflict in world["conflicts"]:
        value = _clamp(_clamp(conflict["intensity"]) * .35
                       + _clamp(conflict["economic_disruption_index"]) * .35
                       + _clamp(conflict["logistics_strain_index"]) * .30)
        for key in ("region_a", "region_b"):
            region_id = conflict[key]
            if result[region_id] is None:
                raise ValueError("incomplete conflict selection cannot emit conflicts")
            result[region_id] = max(result[region_id], value)
    return result


def networks_and_exchanges(world: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a previously audited, complete native/economy source domain."""
    regions = world["political_regions"]
    economies = {row["region_id"]: row for row in world["economy_histories"]}
    if set(economies) != {region["id"] for region in regions}:
        raise ValueError("complete regional economy coverage required")
    final_steps = {}
    for region_id, economy in economies.items():
        if not economy["steps"]:
            raise ValueError("actual economy era steps required")
        final_steps[region_id] = economy["steps"][-1]
    routes = {row["id"]: row for row in world["routes"]}
    trades = {row["id"]: row for row in world["trade_flows"]}
    settlements = {row["id"]: row["region_id"] for row in world["settlements"]}
    route_ids = {region["id"]: set() for region in regions}
    trade_ids = {region["id"]: set() for region in regions}
    border_ids = {region["id"]: set() for region in regions}
    for route_id, route in routes.items():
        for region_id in {settlements[route[key]] for key in ("from", "to")}:
            route_ids[region_id].add(route_id)
    for trade_id, trade in trades.items():
        for region_id in {trade["region_from"], trade["region_to"]}:
            trade_ids[region_id].add(trade_id)
    for border in world["borders"]:
        for key in ("region_a", "region_b"):
            border_ids[border[key]].add(border["id"])
    pressures = _conflict_pressure(world)
    max_routes = max((len(ids) for ids in route_ids.values()), default=1)
    networks = []
    for region in sorted(regions, key=lambda row: row["id"]):
        region_id = region["id"]
        local_routes = sorted(route_ids[region_id])
        local_trades = sorted(trade_ids[region_id])
        local_borders = sorted(border_ids[region_id])
        economy = economies[region_id]
        step = final_steps[region_id]
        distance = sum(routes[key]["distance_km"] for key in local_routes)
        cost = sum(routes[key]["cost"] for key in local_routes)
        volume = sum(trades[key]["volume_index"] for key in local_trades)
        interregional = sum(trades[key]["volume_index"] for key in local_trades if trades[key]["interregional"])
        density = _clamp(len(local_routes) / max(1, max_routes))
        efficiency = _clamp(_clamp(distance / max(cost, 1.0)) * .72 + density * .28)
        prosperity = _calculate(_clamp, _estimate(step, "prosperity_index"))
        dependency = _calculate(_clamp, _estimate(step, "trade_dependency_index"))
        output = _estimate(economy, "peak_gross_output_index")
        army = _estimate(economy, "max_army_capacity_population")
        treasury = _estimate(economy, "peak_treasury_index")
        pressure = pressures[region_id]
        supply = _calculate(lambda o, a, d: _clamp(o / 1200 * .34 + a / 25_000_000 * .24 + density * .24 + d * .18), output, army, dependency)
        resilience = _calculate(lambda p, t, c: _clamp(efficiency * .34 + p * .24 + t / 180 * .18 + (1 - c) * .24), prosperity, treasury, pressure)
        friction = sum(trades[key]["friction"] for key in local_trades) / max(1, len(local_trades))
        exposure = _calculate(lambda p: _clamp(friction * .36 + len(local_borders) / max(1, len(local_borders) + len(local_routes)) * .22 + p * .42), pressure)
        networks.append(_record({
            "id": len(networks), "region_id": region_id,
            "route_ids": local_routes, "trade_flow_ids": local_trades, "border_ids": local_borders,
            "route_count": len(local_routes), "trade_flow_count": len(local_trades), "border_count": len(local_borders),
        }, {
            "total_route_distance_km": distance, "total_route_cost": cost,
            "total_trade_volume_index": volume, "interregional_trade_volume_index": interregional,
            "army_capacity_population": army, "supply_capacity_index": supply,
            "transport_efficiency_index": efficiency, "logistics_resilience_index": resilience,
            "chokepoint_exposure_index": exposure,
        }))
    by_region = {row["region_id"]: row for row in networks}
    exchanges = []
    for trade_id, trade in sorted(trades.items()):
        source, target = trade["region_from"], trade["region_to"]
        source_step, target_step = final_steps[source], final_steps[target]
        volume, friction, distance = max(0.0, trade["volume_index"]), _clamp(trade["friction"]), max(0.0, trade["distance_km"])
        source_prosperity = _calculate(_clamp, _estimate(source_step, "prosperity_index"))
        target_dependency = _calculate(_clamp, _estimate(target_step, "trade_dependency_index"))
        supply = _calculate(lambda r, p: _clamp(r / 260 * .30 + p * .32 + volume / 140 * .20 + (1 - friction) * .18), _estimate(source_step, "resource_output_index"), source_prosperity)
        demand = _calculate(lambda p, t, u: _clamp(p / 1_000_000_000 * .28 + t * .34 + volume / 140 * .18 + u / 260 * .20), _estimate(target_step, "population"), target_dependency, _estimate(target_step, "urban_services_index"))
        pressure = _calculate(max, pressures[source], pressures[target])
        disruption = _calculate(lambda p: _clamp(friction * .36 + p * .44 + distance / 9000 * .20), pressure)
        spread = _calculate(lambda d, s: _clamp(friction * .48 + abs(d - s) * .28 + distance / 9000 * .24), demand, supply)
        network_access = (by_region[source]["transport_efficiency_index"] + by_region[target]["transport_efficiency_index"]) * .5
        access = _calculate(lambda d: _clamp((1 - friction) * .32 + volume / 140 * .24 + network_access * .28 + (1 - d) * .16), disruption)
        food = _calculate(lambda a, b: _clamp((a + b) * .5), _estimate(source_step, "food_security_index"), _estimate(target_step, "food_security_index"))
        tax = _calculate(lambda d: max(0.0, volume * (.035 + (.018 if trade["interregional"] else 0)) * (1 - d * .20)), disruption)
        exchanges.append(_record({
            "id": len(exchanges), "trade_flow_id": trade_id, "route_id": trade["route_id"],
            "from_settlement_id": trade["from"], "to_settlement_id": trade["to"],
            "region_from": source, "region_to": target,
            "primary_good": trade["primary_good"], "interregional": trade["interregional"],
        }, {
            "distance_km": distance, "volume_index": volume, "friction": friction,
            "supply_index": supply, "demand_index": demand, "price_spread_index": spread,
            "market_access_index": access, "tax_revenue_index": tax,
            "food_security_link_index": food, "disruption_risk_index": disruption,
        }))
    summary = {
        "logistics_network_count": len(networks), "logistics_route_link_count": sum(len(ids) for ids in route_ids.values()),
        "market_exchange_count": len(exchanges), "interregional_market_exchange_count": sum(row["interregional"] for row in exchanges),
        "total_market_exchange_volume_index": _aggregate(exchanges, "volume_index"),
        "mean_logistics_transport_efficiency_index": _aggregate(networks, "transport_efficiency_index", mean=True),
        "mean_logistics_resilience_index": _aggregate(networks, "logistics_resilience_index", mean=True),
        "mean_market_access_index": _aggregate(exchanges, "market_access_index", mean=True),
        "mean_market_disruption_risk_index": _aggregate(exchanges, "disruption_risk_index", mean=True),
    }
    summary["logistics_summary_availability"] = {key: value is not None for key, value in summary.items()}
    return {"logistics_networks": networks, "market_exchanges": exchanges, "summary": summary}


def enrich_available_logistics(world: dict[str, Any]) -> dict[str, Any]:
    from .campaign_availability import campaign_records
    from .logistics_availability_validation import (
        require_logistics_sources, logistics_model_v2, campaign_model_v2,
        validate_logistics_availability, uses_logistics_availability,
    )
    from .campaign_availability_validation import validate_campaign_availability

    if not uses_logistics_availability(world):
        raise ValueError("native availability source required for logistics successor")
    require_logistics_sources(world)
    if "logistics_exchange_model" in world:
        for audit in (validate_logistics_availability, validate_campaign_availability):
            errors = audit(world)
            if errors:
                raise ValueError("invalid existing logistics publication: " + "; ".join(errors))
        return world
    logistics = networks_and_exchanges(world)
    campaigns = campaign_records(world, {row["region_id"]: row for row in logistics["logistics_networks"]})
    staged = dict(world)
    staged.update({key: value for key, value in logistics.items() if key != "summary"})
    staged.update({key: value for key, value in campaigns.items() if key != "summary"})
    staged["summary"] = {**world["summary"], **logistics["summary"], **campaigns["summary"]}
    for key, declaration in (("logistics_exchange_model", logistics_model_v2()), ("campaign_operations_model", campaign_model_v2())):
        staged[key] = declaration
        staged["summary"][key] = declaration["model_type"]
    for audit in (validate_logistics_availability, validate_campaign_availability):
        errors = audit(staged)
        if errors:
            raise ValueError("invalid computed logistics publication: " + "; ".join(errors))
    publication = {key: value for key, value in staged.items() if key not in world or value is not world[key]}
    # All parent/source records and their objects stay untouched. Only the owned
    # conflict link dictionaries, output collections and summary are published.
    world.update(publication)
    return world
