from __future__ import annotations

from typing import Any


LOGISTICS_EXCHANGE_MODEL = "causal_region_route_trade_economy_logistics_exchange_v1"


def _logistics_exchange_model() -> dict[str, Any]:
    return {
        "model_type": LOGISTICS_EXCHANGE_MODEL,
        "deterministic": True,
        "region_order": "ascending_political_region_id_v1",
        "network_model": "incident_route_trade_border_economy_conflict_logistics_v1",
        "transport_model": "route_distance_cost_density_efficiency_v1",
        "capacity_model": "economy_army_route_trade_supply_and_resilience_v1",
        "exchange_model": "trade_flow_economy_network_supply_demand_access_disruption_v1",
        "model_limitation": "aggregate_static_logistics_and_exchange_indices_without_inventory_vehicle_fleet_or_dynamic_congestion",
    }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _economy_by_region(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    economies: dict[int, dict[str, Any]] = {}
    for history in payload.get("economy_histories", []):
        region_id = int(history.get("region_id", -1))
        if region_id >= 0:
            economies[region_id] = history
    return economies


def _final_step(economy: dict[str, Any]) -> dict[str, Any]:
    steps = economy.get("steps", [])
    if isinstance(steps, list) and steps:
        return steps[-1]
    return {}


def _settlement_regions(payload: dict[str, Any]) -> dict[int, int]:
    regions: dict[int, int] = {}
    for settlement in payload.get("settlements", []):
        settlement_id = int(settlement.get("id", -1))
        region_id = int(settlement.get("region_id", -1))
        if settlement_id >= 0 and region_id >= 0:
            regions[settlement_id] = region_id
    return regions


def _conflict_pressure_by_region(payload: dict[str, Any]) -> dict[int, float]:
    pressure: dict[int, float] = {}
    for conflict in payload.get("conflicts", []):
        disruption = _clamp(float(conflict.get("economic_disruption_index", 0.0)))
        strain = _clamp(float(conflict.get("logistics_strain_index", 0.0)))
        intensity = _clamp(float(conflict.get("intensity", 0.0)))
        value = _clamp(intensity * 0.35 + disruption * 0.35 + strain * 0.30)
        for key in ("region_a", "region_b"):
            region_id = int(conflict.get(key, -1))
            if region_id >= 0:
                pressure[region_id] = max(pressure.get(region_id, 0.0), value)
    return pressure


def _route_regions(route: dict[str, Any], settlement_regions: dict[int, int]) -> set[int]:
    regions: set[int] = set()
    for key in ("from", "to"):
        region_id = settlement_regions.get(int(route.get(key, -1)), -1)
        if region_id >= 0:
            regions.add(region_id)
    return regions


def _trade_regions(trade: dict[str, Any]) -> set[int]:
    regions: set[int] = set()
    for key in ("region_from", "region_to"):
        region_id = int(trade.get(key, -1))
        if region_id >= 0:
            regions.add(region_id)
    return regions


def _index_records(records: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        record_id = int(record.get("id", -1))
        if record_id >= 0:
            indexed[record_id] = record
    return indexed


def _expected_logistics_exchanges(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    regions = payload["political_regions"]
    routes = payload["routes"]
    trade_flows = payload["trade_flows"]
    economies = _economy_by_region(payload)
    settlement_regions = _settlement_regions(payload)
    conflict_pressure = _conflict_pressure_by_region(payload)
    route_by_id = _index_records(routes)
    trade_by_id = _index_records(trade_flows)

    route_ids_by_region: dict[int, set[int]] = {}
    for route in routes:
        route_id = int(route.get("id", -1))
        if route_id < 0:
            continue
        for region_id in _route_regions(route, settlement_regions):
            route_ids_by_region.setdefault(region_id, set()).add(route_id)

    trade_ids_by_region: dict[int, set[int]] = {}
    for trade in trade_flows:
        trade_id = int(trade.get("id", -1))
        if trade_id < 0:
            continue
        for region_id in _trade_regions(trade):
            trade_ids_by_region.setdefault(region_id, set()).add(trade_id)

    border_ids_by_region: dict[int, set[int]] = {}
    for border in payload["borders"]:
        border_id = int(border.get("id", -1))
        if border_id < 0:
            continue
        for key in ("region_a", "region_b"):
            region_id = int(border.get(key, -1))
            if region_id >= 0:
                border_ids_by_region.setdefault(region_id, set()).add(border_id)

    networks: list[dict[str, Any]] = []
    network_by_region: dict[int, dict[str, Any]] = {}
    total_route_links = 0
    efficiency_sum = 0.0
    resilience_sum = 0.0
    max_route_count = max((len(ids) for ids in route_ids_by_region.values()), default=1)
    for region in sorted(regions, key=lambda item: int(item.get("id", -1))):
        region_id = int(region.get("id", -1))
        if region_id < 0:
            continue
        route_ids = sorted(route_ids_by_region.get(region_id, set()))
        trade_ids = sorted(trade_ids_by_region.get(region_id, set()))
        border_ids = sorted(border_ids_by_region.get(region_id, set()))
        economy = economies.get(region_id, {})
        final_step = _final_step(economy)
        route_distance = sum(
            float(route_by_id[route_id].get("distance_km", 0.0))
            for route_id in route_ids
            if route_id in route_by_id
        )
        route_cost = sum(
            float(route_by_id[route_id].get("cost", 0.0))
            for route_id in route_ids
            if route_id in route_by_id
        )
        trade_volume = sum(
            float(trade_by_id[trade_id].get("volume_index", 0.0))
            for trade_id in trade_ids
            if trade_id in trade_by_id
        )
        interregional_trade = sum(
            float(trade_by_id[trade_id].get("volume_index", 0.0))
            for trade_id in trade_ids
            if trade_id in trade_by_id
            and bool(trade_by_id[trade_id].get("interregional", False))
        )
        route_efficiency = _clamp(route_distance / max(route_cost, 1.0))
        route_density = _clamp(len(route_ids) / max(1, max_route_count))
        transport_efficiency = _clamp(route_efficiency * 0.72 + route_density * 0.28)
        prosperity = _clamp(float(final_step.get("prosperity_index", 0.0)))
        trade_dependency = _clamp(float(final_step.get("trade_dependency_index", 0.0)))
        peak_output = float(
            economy.get(
                "peak_gross_output_index", economy.get("final_gross_output_index", 0.0)
            )
        )
        peak_army = float(economy.get("max_army_capacity_population", 0.0))
        treasury = float(
            economy.get("peak_treasury_index", economy.get("final_treasury_index", 0.0))
        )
        pressure = conflict_pressure.get(region_id, 0.0)
        supply_capacity = _clamp(
            peak_output / 1200.0 * 0.34
            + peak_army / 25_000_000.0 * 0.24
            + route_density * 0.24
            + trade_dependency * 0.18
        )
        resilience = _clamp(
            transport_efficiency * 0.34
            + prosperity * 0.24
            + treasury / 180.0 * 0.18
            + (1.0 - pressure) * 0.24
        )
        mean_trade_friction = sum(
            float(trade_by_id[trade_id].get("friction", 0.0))
            for trade_id in trade_ids
            if trade_id in trade_by_id
        ) / max(1, len(trade_ids))
        chokepoint_exposure = _clamp(
            mean_trade_friction * 0.36
            + len(border_ids) / max(1, len(border_ids) + len(route_ids)) * 0.22
            + pressure * 0.42
        )
        network = {
            "id": len(networks),
            "region_id": region_id,
            "route_ids": route_ids,
            "trade_flow_ids": trade_ids,
            "border_ids": border_ids,
            "route_count": len(route_ids),
            "trade_flow_count": len(trade_ids),
            "border_count": len(border_ids),
            "total_route_distance_km": round(route_distance, 6),
            "total_route_cost": round(route_cost, 6),
            "total_trade_volume_index": round(trade_volume, 6),
            "interregional_trade_volume_index": round(interregional_trade, 6),
            "army_capacity_population": round(peak_army, 6),
            "supply_capacity_index": round(supply_capacity, 6),
            "transport_efficiency_index": round(transport_efficiency, 6),
            "logistics_resilience_index": round(resilience, 6),
            "chokepoint_exposure_index": round(chokepoint_exposure, 6),
        }
        networks.append(network)
        network_by_region[region_id] = network
        total_route_links += len(route_ids)
        efficiency_sum += transport_efficiency
        resilience_sum += resilience

    exchanges: list[dict[str, Any]] = []
    market_access_sum = 0.0
    disruption_sum = 0.0
    total_market_volume = 0.0
    interregional_market_count = 0
    for trade in sorted(trade_flows, key=lambda item: int(item.get("id", -1))):
        trade_id = int(trade.get("id", -1))
        route_id = int(trade.get("route_id", -1))
        source_region = int(trade.get("region_from", -1))
        target_region = int(trade.get("region_to", -1))
        route = route_by_id.get(route_id, {})
        source_economy = _final_step(economies.get(source_region, {}))
        target_economy = _final_step(economies.get(target_region, {}))
        volume = max(0.0, float(trade.get("volume_index", 0.0)))
        friction = _clamp(float(trade.get("friction", 0.0)))
        distance = max(
            0.0,
            float(trade.get("distance_km", route.get("distance_km", 0.0))),
        )
        source_prosperity = _clamp(float(source_economy.get("prosperity_index", 0.0)))
        target_trade_dependency = _clamp(
            float(target_economy.get("trade_dependency_index", 0.0))
        )
        source_resource_output = float(source_economy.get("resource_output_index", 0.0))
        target_population = float(target_economy.get("population", 0.0))
        supply_index = _clamp(
            source_resource_output / 260.0 * 0.30
            + source_prosperity * 0.32
            + volume / 140.0 * 0.20
            + (1.0 - friction) * 0.18
        )
        demand_index = _clamp(
            target_population / 1_000_000_000.0 * 0.28
            + target_trade_dependency * 0.34
            + volume / 140.0 * 0.18
            + float(target_economy.get("urban_services_index", 0.0)) / 260.0 * 0.20
        )
        regional_pressure = max(
            conflict_pressure.get(source_region, 0.0),
            conflict_pressure.get(target_region, 0.0),
        )
        disruption_risk = _clamp(
            friction * 0.36 + regional_pressure * 0.44 + distance / 9000.0 * 0.20
        )
        price_spread = _clamp(
            friction * 0.48
            + abs(demand_index - supply_index) * 0.28
            + distance / 9000.0 * 0.24
        )
        source_network = network_by_region.get(source_region, {})
        target_network = network_by_region.get(target_region, {})
        network_access = (
            float(source_network.get("transport_efficiency_index", 0.0))
            + float(target_network.get("transport_efficiency_index", 0.0))
        ) * 0.5
        market_access = _clamp(
            (1.0 - friction) * 0.32
            + volume / 140.0 * 0.24
            + network_access * 0.28
            + (1.0 - disruption_risk) * 0.16
        )
        food_security_link = _clamp(
            (
                float(source_economy.get("food_security_index", 0.0))
                + float(target_economy.get("food_security_index", 0.0))
            )
            * 0.5
        )
        tax_revenue = max(
            0.0,
            volume
            * (0.035 + (0.018 if bool(trade.get("interregional", False)) else 0.0))
            * (1.0 - disruption_risk * 0.20),
        )
        exchanges.append(
            {
                "id": len(exchanges),
                "trade_flow_id": trade_id,
                "route_id": route_id,
                "from_settlement_id": int(trade.get("from", route.get("from", -1))),
                "to_settlement_id": int(trade.get("to", route.get("to", -1))),
                "region_from": source_region,
                "region_to": target_region,
                "primary_good": str(trade.get("primary_good", "mixed_goods")),
                "interregional": bool(trade.get("interregional", False)),
                "distance_km": round(distance, 6),
                "volume_index": round(volume, 6),
                "friction": round(friction, 6),
                "supply_index": round(supply_index, 6),
                "demand_index": round(demand_index, 6),
                "price_spread_index": round(price_spread, 6),
                "market_access_index": round(market_access, 6),
                "tax_revenue_index": round(tax_revenue, 6),
                "food_security_link_index": round(food_security_link, 6),
                "disruption_risk_index": round(disruption_risk, 6),
            }
        )
        market_access_sum += market_access
        disruption_sum += disruption_risk
        total_market_volume += volume
        interregional_market_count += int(bool(trade.get("interregional", False)))

    network_count = len(networks)
    market_count = len(exchanges)
    summary = {
        "logistics_network_count": network_count,
        "logistics_route_link_count": total_route_links,
        "market_exchange_count": market_count,
        "interregional_market_exchange_count": interregional_market_count,
        "total_market_exchange_volume_index": round(total_market_volume, 6),
        "mean_logistics_transport_efficiency_index": round(
            efficiency_sum / network_count, 6
        )
        if network_count
        else 0.0,
        "mean_logistics_resilience_index": round(resilience_sum / network_count, 6)
        if network_count
        else 0.0,
        "mean_market_access_index": round(market_access_sum / market_count, 6)
        if market_count
        else 0.0,
        "mean_market_disruption_risk_index": round(disruption_sum / market_count, 6)
        if market_count
        else 0.0,
    }
    return networks, exchanges, summary


def _contains_expected(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_expected(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _contains_expected(actual_item, expected_item)
                for actual_item, expected_item in zip(actual, expected, strict=True)
            )
        )
    return actual == expected


def validate_logistics_exchange_replay(payload: dict[str, Any]) -> list[str]:
    try:
        summary = payload.get("summary", {})
        required_lists = (
            "political_regions",
            "routes",
            "trade_flows",
            "economy_histories",
            "settlements",
            "conflicts",
            "borders",
            "logistics_networks",
            "market_exchanges",
        )
        valid = isinstance(summary, dict) and all(
            isinstance(payload.get(name), list) for name in required_lists
        )
        valid = valid and payload.get("logistics_exchange_model") == _logistics_exchange_model()
        valid = valid and summary.get("logistics_exchange_model") == LOGISTICS_EXCHANGE_MODEL
        networks, exchanges, expected_summary = _expected_logistics_exchanges(payload)
        valid = valid and _contains_expected(payload.get("logistics_networks"), networks)
        valid = valid and _contains_expected(payload.get("market_exchanges"), exchanges)
        valid = valid and all(
            summary.get(key) == value for key, value in expected_summary.items()
        )
    except (
        AttributeError,
        IndexError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
        ZeroDivisionError,
    ):
        valid = False
    return [] if valid else ["logistics exchange model or causal replay invalid"]
