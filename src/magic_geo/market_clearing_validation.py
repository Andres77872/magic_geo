from __future__ import annotations

from typing import Any

from .demographic_agents_validation import _expected_aggregate_agents
from .logistics_exchange_validation import _expected_logistics_exchanges


ROUTE_CAPACITY_MULTIPLIER = {
    "coastal_sea": 1.35,
    "river": 1.18,
    "river_corridor": 1.18,
    "overland": 0.82,
    "mountain_pass": 0.62,
    "desert_track": 0.56,
}
ORDER_KIND_BY_SECTOR = {
    "agriculture": "producer_supply",
    "resource": "producer_supply",
    "trade": "broker_supply",
    "urban_services": "service_supply",
    "administration": "state_demand",
}
MARKET_CLEARING_MODEL = (
    "causal_route_capacity_agent_orders_price_iteration_inventory_learning_market_clearing_v1"
)


def _market_clearing_model() -> dict[str, Any]:
    return {
        "model_type": MARKET_CLEARING_MODEL,
        "deterministic": True,
        "route_capacity_model": "route_mode_network_firm_capacity_distance_friction_v1",
        "order_model": "three_source_firms_three_target_households_and_state_tax_demand_v1",
        "clearing_model": "proportional_route_capacity_allocation_v1",
        "price_model": "three_step_supply_demand_price_interpolation_v1",
        "inventory_model": "three_step_expectation_learning_supply_demand_response_v1",
        "annotation_model": "route_and_market_exchange_clearing_backreferences_v1",
        "model_limitation": "single_deterministic_clearing_episode_without_repeated_period_equilibrium_entry_exit_bargaining_or_empirical_calibration",
    }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _index(records: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        record_id = int(record.get("id", -1))
        if record_id >= 0:
            indexed[record_id] = record
    return indexed


def _by_region(records: list[dict[str, Any]], key: str = "region_id") -> dict[int, dict[str, Any]]:
    indexed: dict[int, dict[str, Any]] = {}
    for record in records:
        region_id = int(record.get(key, -1))
        if region_id >= 0:
            indexed[region_id] = record
    return indexed


def _firm_capacity_by_region(firms: list[dict[str, Any]]) -> dict[int, float]:
    capacity: dict[int, float] = {}
    for firm in firms:
        region_id = int(firm.get("region_id", -1))
        if region_id >= 0:
            capacity[region_id] = capacity.get(region_id, 0.0) + float(
                firm.get("output_index", 0.0)
            )
    return capacity


def _household_pressure_by_region(households: list[dict[str, Any]]) -> dict[int, float]:
    pressure_sum: dict[int, float] = {}
    population_sum: dict[int, float] = {}
    for cohort in households:
        region_id = int(cohort.get("region_id", -1))
        population = max(0.0, float(cohort.get("population", 0.0)))
        if region_id >= 0:
            pressure_sum[region_id] = pressure_sum.get(region_id, 0.0) + float(
                cohort.get("consumption_pressure_index", 0.0)
            ) * population
            population_sum[region_id] = population_sum.get(region_id, 0.0) + population
    return {
        region_id: pressure_sum.get(region_id, 0.0) / max(1.0, population)
        for region_id, population in population_sum.items()
    }


def _group_by_region(records: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        region_id = int(record.get("region_id", -1))
        if region_id >= 0:
            grouped.setdefault(region_id, []).append(record)
    for region_records in grouped.values():
        region_records.sort(key=lambda record: int(record.get("id", -1)))
    return grouped


def _route_multiplier(route: dict[str, Any]) -> float:
    route_type = str(route.get("type", "overland"))
    return ROUTE_CAPACITY_MULTIPLIER.get(route_type, 0.76)


def _expected_market_clearing(
    payload: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[str, Any],
]:
    networks, base_exchanges, _ = _expected_logistics_exchanges(payload)
    households, firms, _, _, _, _ = _expected_aggregate_agents(payload)
    exchanges = [dict(exchange) for exchange in base_exchanges]
    routes = [dict(route) for route in payload["routes"]]
    for route in routes:
        route.pop("route_capacity_constraint_id", None)
        route.pop("market_capacity_volume_index", None)
        route.pop("market_capacity_utilization_index", None)
    routes_by_id = _index(routes)
    logistics_by_region = _by_region(networks)
    firm_capacity_by_region = _firm_capacity_by_region(firms)
    household_pressure_by_region = _household_pressure_by_region(households)
    households_by_region = _group_by_region(households)
    firms_by_region = _group_by_region(firms)

    exchange_ids_by_route: dict[int, list[int]] = {}
    for exchange in exchanges:
        route_id = int(exchange.get("route_id", -1))
        exchange_id = int(exchange.get("id", -1))
        if route_id >= 0 and exchange_id >= 0:
            exchange_ids_by_route.setdefault(route_id, []).append(exchange_id)
    market_by_id = _index(exchanges)

    constraints: list[dict[str, Any]] = []
    constraint_by_route: dict[int, dict[str, Any]] = {}
    total_requested_volume = 0.0
    total_cleared_volume = 0.0
    total_unmet_volume = 0.0
    route_utilization_sum = 0.0
    for route_id in sorted(exchange_ids_by_route):
        route = routes_by_id.get(route_id, {})
        exchange_ids = sorted(exchange_ids_by_route.get(route_id, []))
        requested_volume = sum(
            float(market_by_id[exchange_id].get("volume_index", 0.0))
            for exchange_id in exchange_ids
        )
        region_ids = {
            int(market_by_id[exchange_id].get(key, -1))
            for exchange_id in exchange_ids
            for key in ("region_from", "region_to")
            if int(market_by_id[exchange_id].get(key, -1)) >= 0
        }
        mean_transport = sum(
            float(
                logistics_by_region.get(region_id, {}).get(
                    "transport_efficiency_index", 0.0
                )
            )
            for region_id in region_ids
        ) / max(1, len(region_ids))
        mean_resilience = sum(
            float(
                logistics_by_region.get(region_id, {}).get(
                    "logistics_resilience_index", 0.0
                )
            )
            for region_id in region_ids
        ) / max(1, len(region_ids))
        mean_pressure = sum(
            household_pressure_by_region.get(region_id, 0.0) for region_id in region_ids
        ) / max(1, len(region_ids))
        firm_capacity = sum(
            firm_capacity_by_region.get(region_id, 0.0) for region_id in region_ids
        )
        distance = max(0.0, float(route.get("distance_km", 0.0)))
        cost = max(0.0, float(route.get("cost", distance)))
        friction = sum(
            float(market_by_id[exchange_id].get("friction", 0.0))
            for exchange_id in exchange_ids
        ) / max(1, len(exchange_ids))
        base_capacity = (
            28.0
            + _route_multiplier(route) * 48.0
            + mean_transport * 32.0
            + mean_resilience * 28.0
            + firm_capacity * 0.035
        )
        capacity_volume = max(
            8.0,
            base_capacity
            / (
                1.0
                + distance / 7000.0
                + friction * 0.38
                + cost / max(1.0, distance + 1.0) * 0.08
            ),
        )
        cleared_volume = min(requested_volume, capacity_volume)
        unmet_volume = max(0.0, requested_volume - cleared_volume)
        utilization = _clamp(cleared_volume / max(1.0, capacity_volume))
        shortage = _clamp(unmet_volume / max(1.0, requested_volume))
        congestion = _clamp(
            utilization * 0.52 + shortage * 0.38 + friction * 0.10
        )
        spoilage = _clamp(
            friction * 0.28
            + shortage * 0.34
            + mean_pressure * 0.20
            + distance / 12000.0 * 0.18
        )
        constraint = {
            "id": len(constraints),
            "route_id": route_id,
            "route_type": str(route.get("type", "unknown")),
            "market_exchange_ids": exchange_ids,
            "market_exchange_count": len(exchange_ids),
            "distance_km": round(distance, 6),
            "requested_volume_index": round(requested_volume, 6),
            "capacity_volume_index": round(capacity_volume, 6),
            "cleared_volume_index": round(cleared_volume, 6),
            "unmet_volume_index": round(unmet_volume, 6),
            "utilization_index": round(utilization, 6),
            "congestion_index": round(congestion, 6),
            "shortage_index": round(shortage, 6),
            "spoilage_loss_index": round(spoilage, 6),
        }
        route["route_capacity_constraint_id"] = constraint["id"]
        route["market_capacity_volume_index"] = constraint["capacity_volume_index"]
        route["market_capacity_utilization_index"] = constraint["utilization_index"]
        constraints.append(constraint)
        constraint_by_route[route_id] = constraint
        total_requested_volume += requested_volume
        total_cleared_volume += cleared_volume
        total_unmet_volume += unmet_volume
        route_utilization_sum += utilization

    clearing_records: list[dict[str, Any]] = []
    orders: list[dict[str, Any]] = []
    price_iterations: list[dict[str, Any]] = []
    inventory_histories: list[dict[str, Any]] = []
    price_adjustment_sum = 0.0
    rationing_sum = 0.0
    clearance_fraction_sum = 0.0
    constrained_records = 0
    endogenous_supply_sum = 0.0
    endogenous_demand_sum = 0.0
    price_iteration_residual_sum = 0.0
    inventory_step_count = 0
    inventory_gap_sum = 0.0
    inventory_learning_sum = 0.0
    inventory_pressure_sum = 0.0
    high_inventory_stress_count = 0
    producer_order_count = 0
    consumer_order_count = 0
    for exchange in sorted(exchanges, key=lambda item: int(item.get("id", -1))):
        exchange_id = int(exchange.get("id", -1))
        route_id = int(exchange.get("route_id", -1))
        constraint = constraint_by_route.get(route_id, {})
        region_from = int(exchange.get("region_from", -1))
        region_to = int(exchange.get("region_to", -1))
        requested = max(0.0, float(exchange.get("volume_index", 0.0)))
        route_requested = max(
            1.0, float(constraint.get("requested_volume_index", requested))
        )
        route_cleared = float(constraint.get("cleared_volume_index", requested))
        cleared = min(requested, requested * route_cleared / route_requested)
        unmet = max(0.0, requested - cleared)
        clearance_fraction = _clamp(cleared / max(1.0, requested))
        rationing = _clamp(unmet / max(1.0, requested))
        utilization = _clamp(float(constraint.get("utilization_index", 0.0)))
        congestion = _clamp(float(constraint.get("congestion_index", 0.0)))
        price_adjustment = _clamp(
            float(exchange.get("price_spread_index", 0.0)) * 0.36
            + congestion * 0.30
            + rationing * 0.24
            + float(exchange.get("disruption_risk_index", 0.0)) * 0.10
        )
        producer_surplus = _clamp(
            float(exchange.get("supply_index", 0.0))
            * clearance_fraction
            * (1.0 + price_adjustment * 0.16)
        )
        consumer_welfare = _clamp(
            float(exchange.get("market_access_index", 0.0))
            * (1.0 - rationing * 0.72)
            * (1.0 - price_adjustment * 0.18)
        )
        order_ids: list[int] = []
        producer_supply = 0.0
        consumer_demand = 0.0
        price_floor_sum = 0.0
        price_ceiling_sum = 0.0
        producer_count = 0
        consumer_count = 0
        source_firms = firms_by_region.get(region_from, [])[:3]
        if not source_firms:
            source_firms = firms_by_region.get(region_to, [])[:1]
        for firm in source_firms:
            firm_id = int(firm.get("id", -1))
            productivity = _clamp(float(firm.get("productivity_index", 0.0)))
            dependency = _clamp(float(firm.get("market_dependency_index", 0.0)))
            supply_risk = _clamp(float(firm.get("supply_chain_risk_index", 0.0)))
            volume = max(
                0.0,
                requested
                * (0.20 + productivity * 0.20)
                * (1.0 - supply_risk * 0.35)
                / max(1, len(source_firms)),
            )
            price_limit = _clamp(
                0.26
                + dependency * 0.20
                + supply_risk * 0.28
                + float(exchange.get("price_spread_index", 0.0)) * 0.26
            )
            fulfillment = _clamp(
                clearance_fraction * (1.0 - supply_risk * 0.28)
                + productivity * 0.16
            )
            order_id = len(orders)
            orders.append(
                {
                    "id": order_id,
                    "market_exchange_id": exchange_id,
                    "market_clearing_record_id": len(clearing_records),
                    "agent_type": "firm",
                    "agent_id": firm_id,
                    "region_id": region_from,
                    "order_side": "supply",
                    "order_kind": ORDER_KIND_BY_SECTOR.get(
                        str(firm.get("sector", "")), "producer_supply"
                    ),
                    "primary_good": str(exchange.get("primary_good", "mixed_goods")),
                    "requested_volume_index": round(volume, 6),
                    "cleared_volume_index": round(volume * fulfillment, 6),
                    "limit_price_index": round(price_limit, 6),
                    "price_acceptance_index": round(
                        _clamp(
                            1.0 - price_limit * 0.36 + producer_surplus * 0.16
                        ),
                        6,
                    ),
                    "rationing_index": round(_clamp(1.0 - fulfillment), 6),
                    "inventory_change_index": round(
                        _clamp(
                            volume * (1.0 - fulfillment) / max(1.0, requested)
                        ),
                        6,
                    ),
                }
            )
            order_ids.append(order_id)
            producer_supply += volume
            price_floor_sum += price_limit
            producer_count += 1
            producer_order_count += 1
        target_households = households_by_region.get(region_to, [])[:3]
        if not target_households:
            target_households = households_by_region.get(region_from, [])[:1]
        for cohort in target_households:
            cohort_id = int(cohort.get("id", -1))
            consumption = _clamp(
                float(cohort.get("consumption_pressure_index", 0.0))
            )
            vulnerability = _clamp(float(cohort.get("vulnerability_index", 0.0)))
            income = _clamp(float(cohort.get("income_index", 0.0)))
            volume = max(
                0.0,
                requested
                * (0.22 + consumption * 0.24 + vulnerability * 0.10)
                / max(1, len(target_households)),
            )
            price_limit = _clamp(
                0.44
                + income * 0.24
                - vulnerability * 0.10
                + float(exchange.get("market_access_index", 0.0)) * 0.18
            )
            fulfillment = _clamp(
                clearance_fraction * (1.0 - rationing * 0.28) + income * 0.10
            )
            order_id = len(orders)
            orders.append(
                {
                    "id": order_id,
                    "market_exchange_id": exchange_id,
                    "market_clearing_record_id": len(clearing_records),
                    "agent_type": "household_cohort",
                    "agent_id": cohort_id,
                    "region_id": region_to,
                    "order_side": "demand",
                    "order_kind": "consumer_demand",
                    "primary_good": str(exchange.get("primary_good", "mixed_goods")),
                    "requested_volume_index": round(volume, 6),
                    "cleared_volume_index": round(volume * fulfillment, 6),
                    "limit_price_index": round(price_limit, 6),
                    "price_acceptance_index": round(
                        _clamp(price_limit * 0.52 + consumer_welfare * 0.22), 6
                    ),
                    "rationing_index": round(_clamp(1.0 - fulfillment), 6),
                    "inventory_change_index": round(
                        -_clamp(
                            volume * (1.0 - fulfillment) / max(1.0, requested)
                        ),
                        6,
                    ),
                }
            )
            order_ids.append(order_id)
            consumer_demand += volume
            price_ceiling_sum += price_limit
            consumer_count += 1
            consumer_order_count += 1
        tax_order_volume = max(
            0.0,
            requested * float(exchange.get("tax_revenue_index", 0.0)) * 0.08,
        )
        if tax_order_volume > 0.0:
            order_id = len(orders)
            orders.append(
                {
                    "id": order_id,
                    "market_exchange_id": exchange_id,
                    "market_clearing_record_id": len(clearing_records),
                    "agent_type": "state",
                    "agent_id": region_to,
                    "region_id": region_to,
                    "order_side": "demand",
                    "order_kind": "tax_collection",
                    "primary_good": str(exchange.get("primary_good", "mixed_goods")),
                    "requested_volume_index": round(tax_order_volume, 6),
                    "cleared_volume_index": round(
                        tax_order_volume * clearance_fraction, 6
                    ),
                    "limit_price_index": round(
                        _clamp(0.42 + price_adjustment * 0.24), 6
                    ),
                    "price_acceptance_index": round(
                        _clamp(0.50 + clearance_fraction * 0.24), 6
                    ),
                    "rationing_index": round(rationing, 6),
                    "inventory_change_index": 0.0,
                }
            )
            order_ids.append(order_id)
            consumer_demand += tax_order_volume
            price_ceiling_sum += _clamp(0.42 + price_adjustment * 0.24)
            consumer_count += 1
            consumer_order_count += 1
        endogenous_supply = (
            producer_supply
            if producer_supply > 0.0
            else requested * float(exchange.get("supply_index", 0.0))
        )
        endogenous_demand = (
            consumer_demand
            if consumer_demand > 0.0
            else requested * float(exchange.get("demand_index", 0.0))
        )
        equilibrium_price = _clamp(
            (price_floor_sum / max(1, producer_count)) * 0.36
            + (price_ceiling_sum / max(1, consumer_count)) * 0.38
            + price_adjustment * 0.26
        )
        residual = _clamp(
            abs(endogenous_demand - endogenous_supply)
            / max(1.0, endogenous_demand + endogenous_supply)
        )
        price_iteration_ids: list[int] = []
        for iteration_index in range(3):
            progress = (iteration_index + 1) / 3.0
            iteration_price = _clamp(
                equilibrium_price * progress
                + float(exchange.get("price_spread_index", 0.0)) * (1.0 - progress)
            )
            supply_volume = endogenous_supply * _clamp(
                0.72 + iteration_price * 0.18 + progress * 0.10
            )
            demand_volume = endogenous_demand * _clamp(
                1.02
                - iteration_price * 0.16
                - rationing * 0.12
                + progress * 0.04
            )
            imbalance = demand_volume - supply_volume
            iteration_id = len(price_iterations)
            price_iterations.append(
                {
                    "id": iteration_id,
                    "market_exchange_id": exchange_id,
                    "market_clearing_record_id": len(clearing_records),
                    "iteration_index": iteration_index + 1,
                    "order_ids": list(order_ids),
                    "order_count": len(order_ids),
                    "price_index": round(iteration_price, 6),
                    "supply_volume_index": round(supply_volume, 6),
                    "demand_volume_index": round(demand_volume, 6),
                    "imbalance_index": round(imbalance, 6),
                    "excess_demand_index": round(
                        _clamp(max(0.0, imbalance) / max(1.0, demand_volume)), 6
                    ),
                    "price_adjustment_index": round(
                        _clamp(
                            abs(imbalance)
                            / max(1.0, demand_volume + supply_volume)
                            + price_adjustment * 0.24
                        ),
                        6,
                    ),
                }
            )
            price_iteration_ids.append(iteration_id)
        inventory_history_id = len(inventory_histories)
        net_inventory_delta = sum(
            float(orders[order_id].get("inventory_change_index", 0.0))
            for order_id in order_ids
            if 0 <= order_id < len(orders)
        )
        initial_inventory = _clamp(
            float(exchange.get("supply_index", 0.0)) * 0.28
            + clearance_fraction * 0.24
            + (1.0 - rationing) * 0.18
            + utilization * 0.16
            + producer_surplus * 0.14
        )
        target_inventory = _clamp(
            0.26
            + float(exchange.get("demand_index", 0.0)) * 0.22
            + float(exchange.get("market_access_index", 0.0)) * 0.16
            + (1.0 - rationing) * 0.16
            + consumer_welfare * 0.20
        )
        producer_expectation_base = _clamp(
            producer_surplus * 0.35
            + (1.0 - rationing) * 0.25
            + (1.0 - price_adjustment) * 0.20
            + clearance_fraction * 0.20
        )
        consumer_expectation_base = _clamp(
            consumer_welfare * 0.38
            + (1.0 - rationing) * 0.30
            + float(exchange.get("market_access_index", 0.0)) * 0.20
            + (1.0 - price_adjustment) * 0.12
        )
        inventory = initial_inventory
        inventory_steps: list[dict[str, Any]] = []
        pressure_sum = 0.0
        price_expectation_sum = 0.0
        supply_response_sum = 0.0
        demand_adjustment_sum = 0.0
        learning_sum = 0.0
        for sequence_index, iteration_id in enumerate(price_iteration_ids):
            iteration = price_iterations[iteration_id]
            price_index = _clamp(float(iteration.get("price_index", 0.0)))
            learning_rate = _clamp(
                0.16
                + price_adjustment * 0.24
                + residual * 0.22
                + rationing * 0.20
                + abs(net_inventory_delta) * 0.18
            )
            current_gap = abs(inventory - target_inventory)
            producer_expectation = _clamp(
                producer_expectation_base * (1.0 - learning_rate * 0.24)
                + _clamp(
                    float(iteration.get("supply_volume_index", 0.0))
                    / max(1.0, endogenous_supply)
                )
                * learning_rate
                * 0.24
            )
            consumer_expectation = _clamp(
                consumer_expectation_base * (1.0 - learning_rate * 0.24)
                + _clamp(
                    float(iteration.get("demand_volume_index", 0.0))
                    / max(1.0, endogenous_demand)
                )
                * learning_rate
                * 0.24
            )
            supply_response = _clamp(
                _clamp(
                    float(iteration.get("supply_volume_index", 0.0))
                    / max(1.0, endogenous_supply)
                )
                * 0.52
                + producer_expectation * 0.28
                + (1.0 - current_gap) * 0.20
            )
            demand_adjustment = _clamp(
                rationing * 0.28
                + price_index * 0.22
                + (1.0 - clearance_fraction) * 0.18
                + _clamp(
                    float(iteration.get("demand_volume_index", 0.0))
                    / max(1.0, endogenous_demand)
                )
                * 0.16
                + consumer_expectation * 0.16
            )
            inventory = _clamp(
                inventory
                + (target_inventory - inventory) * learning_rate * 0.35
                + net_inventory_delta * 0.28
                + (supply_response - demand_adjustment) * 0.08
            )
            inventory_gap = abs(inventory - target_inventory)
            inventory_pressure = _clamp(
                inventory_gap * 0.45
                + rationing * 0.22
                + residual * 0.18
                + price_index * 0.15
            )
            price_expectation = _clamp(
                producer_expectation * 0.48 + consumer_expectation * 0.52
            )
            inventory_steps.append(
                {
                    "sequence_index": sequence_index,
                    "price_iteration_id": iteration_id,
                    "price_index": round(price_index, 6),
                    "inventory_index": round(inventory, 6),
                    "target_inventory_index": round(target_inventory, 6),
                    "inventory_gap_index": round(inventory_gap, 6),
                    "supply_response_index": round(supply_response, 6),
                    "demand_adjustment_index": round(demand_adjustment, 6),
                    "learning_rate_index": round(learning_rate, 6),
                    "producer_expectation_index": round(producer_expectation, 6),
                    "consumer_expectation_index": round(consumer_expectation, 6),
                    "rationing_memory_index": round(rationing, 6),
                    "clearance_memory_index": round(clearance_fraction, 6),
                }
            )
            pressure_sum += inventory_pressure
            price_expectation_sum += price_expectation
            supply_response_sum += supply_response
            demand_adjustment_sum += demand_adjustment
            learning_sum += learning_rate
        step_divisor = max(1, len(inventory_steps))
        final_inventory = (
            inventory_steps[-1]["inventory_index"]
            if inventory_steps
            else round(initial_inventory, 6)
        )
        final_gap = abs(float(final_inventory) - target_inventory)
        mean_pressure = pressure_sum / step_divisor if inventory_steps else 0.0
        high_stress = bool(mean_pressure >= 0.60 or final_gap >= 0.45)
        inventory_histories.append(
            {
                "id": inventory_history_id,
                "market_clearing_record_id": len(clearing_records),
                "market_exchange_id": exchange_id,
                "trade_flow_id": int(exchange.get("trade_flow_id", -1)),
                "route_id": route_id,
                "region_from": region_from,
                "region_to": region_to,
                "primary_good": str(exchange.get("primary_good", "mixed_goods")),
                "initial_inventory_index": round(initial_inventory, 6),
                "target_inventory_index": round(target_inventory, 6),
                "final_inventory_index": round(float(final_inventory), 6),
                "inventory_gap_index": round(final_gap, 6),
                "learning_rate_index": round(learning_sum / step_divisor, 6)
                if inventory_steps
                else 0.0,
                "mean_inventory_pressure_index": round(mean_pressure, 6),
                "mean_price_expectation_index": round(
                    price_expectation_sum / step_divisor, 6
                )
                if inventory_steps
                else 0.0,
                "mean_supply_response_index": round(
                    supply_response_sum / step_divisor, 6
                )
                if inventory_steps
                else 0.0,
                "mean_demand_adjustment_index": round(
                    demand_adjustment_sum / step_divisor, 6
                )
                if inventory_steps
                else 0.0,
                "high_inventory_stress": high_stress,
                "step_count": len(inventory_steps),
                "steps": inventory_steps,
            }
        )
        inventory_step_count += len(inventory_steps)
        inventory_gap_sum += final_gap
        inventory_learning_sum += (
            learning_sum / step_divisor if inventory_steps else 0.0
        )
        inventory_pressure_sum += mean_pressure
        high_inventory_stress_count += int(high_stress)
        record = {
            "id": len(clearing_records),
            "market_exchange_id": exchange_id,
            "trade_flow_id": int(exchange.get("trade_flow_id", -1)),
            "route_id": route_id,
            "route_capacity_constraint_id": int(constraint.get("id", -1)),
            "region_from": region_from,
            "region_to": region_to,
            "primary_good": str(exchange.get("primary_good", "mixed_goods")),
            "requested_volume_index": round(requested, 6),
            "cleared_volume_index": round(cleared, 6),
            "unmet_demand_index": round(unmet, 6),
            "clearance_fraction": round(clearance_fraction, 6),
            "route_utilization_index": round(utilization, 6),
            "price_adjustment_index": round(price_adjustment, 6),
            "rationing_index": round(rationing, 6),
            "producer_surplus_index": round(producer_surplus, 6),
            "consumer_welfare_index": round(consumer_welfare, 6),
            "agent_order_ids": order_ids,
            "agent_order_count": len(order_ids),
            "price_iteration_ids": price_iteration_ids,
            "price_iteration_count": len(price_iteration_ids),
            "market_inventory_history_id": inventory_history_id,
            "endogenous_supply_index": round(endogenous_supply, 6),
            "endogenous_demand_index": round(endogenous_demand, 6),
            "equilibrium_price_index": round(equilibrium_price, 6),
            "price_residual_index": round(residual, 6),
        }
        exchange["market_clearing_record_id"] = record["id"]
        exchange["cleared_volume_index"] = record["cleared_volume_index"]
        exchange["unmet_demand_index"] = record["unmet_demand_index"]
        exchange["clearance_fraction"] = record["clearance_fraction"]
        exchange["market_inventory_history_id"] = inventory_history_id
        clearing_records.append(record)
        price_adjustment_sum += price_adjustment
        rationing_sum += rationing
        clearance_fraction_sum += clearance_fraction
        constrained_records += int(float(record["unmet_demand_index"]) > 0.0)
        endogenous_supply_sum += endogenous_supply
        endogenous_demand_sum += endogenous_demand
        price_iteration_residual_sum += residual

    route_constraint_count = len(constraints)
    clearing_count = len(clearing_records)
    inventory_count = len(inventory_histories)
    summary = {
        "route_capacity_constraint_count": route_constraint_count,
        "market_clearing_record_count": clearing_count,
        "market_agent_order_count": len(orders),
        "market_price_iteration_count": len(price_iterations),
        "market_inventory_history_count": inventory_count,
        "market_inventory_step_count": inventory_step_count,
        "producer_market_order_count": producer_order_count,
        "consumer_market_order_count": consumer_order_count,
        "constrained_market_exchange_count": constrained_records,
        "total_market_requested_volume_index": round(total_requested_volume, 6),
        "total_market_cleared_volume_index": round(total_cleared_volume, 6),
        "total_market_unmet_demand_index": round(total_unmet_volume, 6),
        "total_endogenous_market_supply_index": round(endogenous_supply_sum, 6),
        "total_endogenous_market_demand_index": round(endogenous_demand_sum, 6),
        "mean_market_clearance_fraction": round(
            clearance_fraction_sum / clearing_count, 6
        )
        if clearing_count
        else 0.0,
        "mean_route_capacity_utilization_index": round(
            route_utilization_sum / route_constraint_count, 6
        )
        if route_constraint_count
        else 0.0,
        "mean_market_price_adjustment_index": round(
            price_adjustment_sum / clearing_count, 6
        )
        if clearing_count
        else 0.0,
        "mean_market_rationing_index": round(rationing_sum / clearing_count, 6)
        if clearing_count
        else 0.0,
        "mean_market_equilibrium_residual_index": round(
            price_iteration_residual_sum / clearing_count, 6
        )
        if clearing_count
        else 0.0,
        "mean_market_inventory_gap_index": round(
            inventory_gap_sum / inventory_count, 6
        )
        if inventory_count
        else 0.0,
        "mean_market_learning_rate_index": round(
            inventory_learning_sum / inventory_count, 6
        )
        if inventory_count
        else 0.0,
        "mean_market_inventory_pressure_index": round(
            inventory_pressure_sum / inventory_count, 6
        )
        if inventory_count
        else 0.0,
        "high_inventory_stress_market_count": high_inventory_stress_count,
    }
    route_annotation_keys = (
        "route_capacity_constraint_id",
        "market_capacity_volume_index",
        "market_capacity_utilization_index",
    )
    exchange_annotation_keys = (
        "market_clearing_record_id",
        "cleared_volume_index",
        "unmet_demand_index",
        "clearance_fraction",
        "market_inventory_history_id",
    )
    route_annotations = {
        int(route.get("id", -1)): {
            key: route[key] for key in route_annotation_keys if key in route
        }
        for route in routes
        if int(route.get("id", -1)) >= 0
    }
    exchange_annotations = {
        int(exchange.get("id", -1)): {
            key: exchange[key] for key in exchange_annotation_keys if key in exchange
        }
        for exchange in exchanges
        if int(exchange.get("id", -1)) >= 0
    }
    return (
        constraints,
        clearing_records,
        orders,
        price_iterations,
        inventory_histories,
        route_annotations,
        exchange_annotations,
        summary,
    )


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


def _validate_market_clearing_legacy(payload: dict[str, Any]) -> list[str]:
    try:
        summary = payload.get("summary", {})
        required_lists = (
            "routes",
            "market_exchanges",
            "logistics_networks",
            "firm_agents",
            "household_cohorts",
            "route_capacity_constraints",
            "market_clearing_records",
            "market_agent_orders",
            "market_price_iterations",
            "market_inventory_histories",
        )
        valid = isinstance(summary, dict) and all(
            isinstance(payload.get(name), list) for name in required_lists
        )
        valid = valid and payload.get("market_clearing_model") == _market_clearing_model()
        valid = valid and summary.get("market_clearing_model") == MARKET_CLEARING_MODEL
        (
            constraints,
            records,
            orders,
            iterations,
            inventories,
            route_annotations,
            exchange_annotations,
            expected_summary,
        ) = _expected_market_clearing(payload)
        valid = valid and _contains_expected(
            payload.get("route_capacity_constraints"), constraints
        )
        valid = valid and _contains_expected(payload.get("market_clearing_records"), records)
        valid = valid and _contains_expected(payload.get("market_agent_orders"), orders)
        valid = valid and _contains_expected(
            payload.get("market_price_iterations"), iterations
        )
        valid = valid and _contains_expected(
            payload.get("market_inventory_histories"), inventories
        )
        valid = valid and all(
            summary.get(key) == value for key, value in expected_summary.items()
        )
        routes_by_id = _index(payload["routes"])
        exchanges_by_id = _index(payload["market_exchanges"])
        valid = valid and all(
            route_id in routes_by_id
            and _contains_expected(routes_by_id[route_id], annotations)
            for route_id, annotations in route_annotations.items()
        )
        valid = valid and all(
            exchange_id in exchanges_by_id
            and _contains_expected(exchanges_by_id[exchange_id], annotations)
            for exchange_id, annotations in exchange_annotations.items()
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
    return [] if valid else ["market clearing model or causal replay invalid"]



def validate_market_clearing_replay(payload: dict[str, Any]) -> list[str]:
    from .market_availability_validation import market_version,validate_market_availability
    try:
        if market_version(payload)==1:
            return _validate_market_clearing_legacy(payload)
        return validate_market_availability(payload)
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,AttributeError):
        return ["market clearing model or causal replay invalid"]
