"""Nullable market equations adapted from their independently retained oracle body."""
from __future__ import annotations
import math
from typing import Any
from .market_clearing_validation import (_index,_by_region,_group_by_region,_route_multiplier,ORDER_KIND_BY_SECTOR)

def _nullable_call(f,*values):
    if any(v is None for v in values):return None
    value=f(*values)
    if type(value) in (int,float) and not math.isfinite(value):raise ValueError("nonfinite demographic replay")
    return value


def _nullable_add(a,b):return _nullable_call(lambda x,y:x+y,a,b)
def _nullable_sub(a,b):return _nullable_call(lambda x,y:x-y,a,b)
def _nullable_mul(a,b):return _nullable_call(lambda x,y:x*y,a,b)
def _nullable_div(a,b):return _nullable_call(lambda x,y:x/y,a,b)
def _nullable_mod(a,b):return _nullable_call(lambda x,y:x%y,a,b)
def _nullable_neg(a):return _nullable_call(lambda x:-x,a)
def _nullable_abs(a):return _nullable_call(abs,a)
def _nullable_float(a):return _nullable_call(float,a)
def _nullable_round(a,n=0):return _nullable_call(lambda x:round(x,n),a)
def _nullable_clamp(a,lower=0.0,upper=1.0):return _nullable_call(lambda x:max(lower,min(upper,x)),a)
def _nullable_sum(values):
    values=list(values)
    return None if any(v is None for v in values) else _nullable_call(sum,values)
def _nullable_max(*values,**kwargs):
    return None if any(v is None for v in values) else max(*values,**kwargs)
def _nullable_min(*values,**kwargs):
    return None if any(v is None for v in values) else min(*values,**kwargs)



def _complete_firm_capacity(world,capacity):
    return {r["id"]:capacity.get(r["id"],0.0) if r["firm_selection_complete"] else None for r in world["political_regions"]}


def _selected_source_firms(world,source,target,grouped):
    regions={r["id"]:r for r in world["political_regions"]}
    if not regions[source]["firm_selection_complete"]:return [],False
    selected=grouped.get(source,[])[:3]
    if selected:return selected,True
    if not regions[target]["firm_selection_complete"]:return [],False
    return grouped.get(target,[])[:1],True

def _firm_capacity_by_region(firms: list[dict[str, Any]]) -> dict[int, float]:
    capacity: dict[int, float] = {}
    for firm in firms:
        region_id = int(firm.get('region_id', _nullable_neg(1)))
        if region_id >= 0:
            capacity[region_id] = _nullable_add(capacity.get(region_id, 0.0), _nullable_float(firm.get('output_index', 0.0)))
    return capacity

def _household_pressure_by_region(households: list[dict[str, Any]]) -> dict[int, float]:
    pressure_sum: dict[int, float] = {}
    population_sum: dict[int, float] = {}
    for cohort in households:
        region_id = int(cohort.get('region_id', _nullable_neg(1)))
        population = _nullable_max(0.0, _nullable_float(cohort.get('population', 0.0)))
        if region_id >= 0:
            pressure_sum[region_id] = _nullable_add(pressure_sum.get(region_id, 0.0), _nullable_mul(_nullable_float(cohort.get('consumption_pressure_index', 0.0)), population))
            population_sum[region_id] = _nullable_add(population_sum.get(region_id, 0.0), population)
    return {region_id: _nullable_div(pressure_sum.get(region_id, 0.0), _nullable_max(1.0, population)) for region_id, population in population_sum.items()}

def _replay_market_numeric(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[str, Any]]:
    networks, base_exchanges = (payload['logistics_networks'], payload['market_exchanges'])
    households, firms = (payload['household_cohorts'], payload['firm_agents'])
    exchanges = [dict(exchange) for exchange in base_exchanges]
    routes = [dict(route) for route in payload['routes']]
    for route in routes:
        route.pop('route_capacity_constraint_id', None)
        route.pop('market_capacity_volume_index', None)
        route.pop('market_capacity_utilization_index', None)
    routes_by_id = _index(routes)
    logistics_by_region = _by_region(networks)
    firm_capacity_by_region = _firm_capacity_by_region(firms)
    firm_capacity_by_region = _complete_firm_capacity(payload, firm_capacity_by_region)
    household_pressure_by_region = _household_pressure_by_region(households)
    households_by_region = _group_by_region(households)
    firms_by_region = _group_by_region(firms)
    exchange_ids_by_route: dict[int, list[int]] = {}
    for exchange in exchanges:
        route_id = int(exchange.get('route_id', _nullable_neg(1)))
        exchange_id = int(exchange.get('id', _nullable_neg(1)))
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
        requested_volume = _nullable_sum((_nullable_float(market_by_id[exchange_id].get('volume_index', 0.0)) for exchange_id in exchange_ids))
        region_ids = {int(market_by_id[exchange_id].get(key, _nullable_neg(1))) for exchange_id in exchange_ids for key in ('region_from', 'region_to') if int(market_by_id[exchange_id].get(key, _nullable_neg(1))) >= 0}
        mean_transport = _nullable_div(_nullable_sum((_nullable_float(logistics_by_region.get(region_id, {}).get('transport_efficiency_index', 0.0)) for region_id in region_ids)), _nullable_max(1, len(region_ids)))
        mean_resilience = _nullable_div(_nullable_sum((_nullable_float(logistics_by_region.get(region_id, {}).get('logistics_resilience_index', 0.0)) for region_id in region_ids)), _nullable_max(1, len(region_ids)))
        mean_pressure = _nullable_div(_nullable_sum((household_pressure_by_region.get(region_id, 0.0) for region_id in region_ids)), _nullable_max(1, len(region_ids)))
        firm_capacity = _nullable_sum((firm_capacity_by_region.get(region_id, 0.0) for region_id in region_ids))
        distance = _nullable_max(0.0, _nullable_float(route.get('distance_km', 0.0)))
        cost = _nullable_max(0.0, _nullable_float(route.get('cost', distance)))
        friction = _nullable_div(_nullable_sum((_nullable_float(market_by_id[exchange_id].get('friction', 0.0)) for exchange_id in exchange_ids)), _nullable_max(1, len(exchange_ids)))
        base_capacity = _nullable_add(_nullable_add(_nullable_add(_nullable_add(28.0, _nullable_mul(_route_multiplier(route), 48.0)), _nullable_mul(mean_transport, 32.0)), _nullable_mul(mean_resilience, 28.0)), _nullable_mul(firm_capacity, 0.035))
        capacity_volume = _nullable_max(8.0, _nullable_div(base_capacity, _nullable_add(_nullable_add(_nullable_add(1.0, _nullable_div(distance, 7000.0)), _nullable_mul(friction, 0.38)), _nullable_mul(_nullable_div(cost, _nullable_max(1.0, _nullable_add(distance, 1.0))), 0.08))))
        cleared_volume = _nullable_min(requested_volume, capacity_volume)
        unmet_volume = _nullable_max(0.0, _nullable_sub(requested_volume, cleared_volume))
        utilization = _nullable_clamp(_nullable_div(cleared_volume, _nullable_max(1.0, capacity_volume)))
        shortage = _nullable_clamp(_nullable_div(unmet_volume, _nullable_max(1.0, requested_volume)))
        congestion = _nullable_clamp(_nullable_add(_nullable_add(_nullable_mul(utilization, 0.52), _nullable_mul(shortage, 0.38)), _nullable_mul(friction, 0.1)))
        spoilage = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(friction, 0.28), _nullable_mul(shortage, 0.34)), _nullable_mul(mean_pressure, 0.2)), _nullable_mul(_nullable_div(distance, 12000.0), 0.18)))
        constraint = {'id': len(constraints), 'route_id': route_id, 'route_type': str(route.get('type', 'unknown')), 'market_exchange_ids': exchange_ids, 'market_exchange_count': len(exchange_ids), 'distance_km': _nullable_round(distance, 6), 'requested_volume_index': _nullable_round(requested_volume, 6), 'capacity_volume_index': _nullable_round(capacity_volume, 6), 'cleared_volume_index': _nullable_round(cleared_volume, 6), 'unmet_volume_index': _nullable_round(unmet_volume, 6), 'utilization_index': _nullable_round(utilization, 6), 'congestion_index': _nullable_round(congestion, 6), 'shortage_index': _nullable_round(shortage, 6), 'spoilage_loss_index': _nullable_round(spoilage, 6)}
        route['route_capacity_constraint_id'] = constraint['id']
        route['market_capacity_volume_index'] = constraint['capacity_volume_index']
        route['market_capacity_utilization_index'] = constraint['utilization_index']
        constraints.append(constraint)
        constraint_by_route[route_id] = constraint
        total_requested_volume = _nullable_add(total_requested_volume, requested_volume)
        total_cleared_volume = _nullable_add(total_cleared_volume, cleared_volume)
        total_unmet_volume = _nullable_add(total_unmet_volume, unmet_volume)
        route_utilization_sum = _nullable_add(route_utilization_sum, utilization)
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
    for exchange in sorted(exchanges, key=lambda item: int(item.get('id', _nullable_neg(1)))):
        exchange_id = int(exchange.get('id', _nullable_neg(1)))
        route_id = int(exchange.get('route_id', _nullable_neg(1)))
        constraint = constraint_by_route.get(route_id, {})
        region_from = int(exchange.get('region_from', _nullable_neg(1)))
        region_to = int(exchange.get('region_to', _nullable_neg(1)))
        requested = _nullable_max(0.0, _nullable_float(exchange.get('volume_index', 0.0)))
        route_requested = _nullable_max(1.0, _nullable_float(constraint.get('requested_volume_index', requested)))
        route_cleared = _nullable_float(constraint.get('cleared_volume_index', requested))
        cleared = _nullable_min(requested, _nullable_div(_nullable_mul(requested, route_cleared), route_requested))
        unmet = _nullable_max(0.0, _nullable_sub(requested, cleared))
        clearance_fraction = _nullable_clamp(_nullable_div(cleared, _nullable_max(1.0, requested)))
        rationing = _nullable_clamp(_nullable_div(unmet, _nullable_max(1.0, requested)))
        utilization = _nullable_clamp(_nullable_float(constraint.get('utilization_index', 0.0)))
        congestion = _nullable_clamp(_nullable_float(constraint.get('congestion_index', 0.0)))
        price_adjustment = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(_nullable_float(exchange.get('price_spread_index', 0.0)), 0.36), _nullable_mul(congestion, 0.3)), _nullable_mul(rationing, 0.24)), _nullable_mul(_nullable_float(exchange.get('disruption_risk_index', 0.0)), 0.1)))
        producer_surplus = _nullable_clamp(_nullable_mul(_nullable_mul(_nullable_float(exchange.get('supply_index', 0.0)), clearance_fraction), _nullable_add(1.0, _nullable_mul(price_adjustment, 0.16))))
        consumer_welfare = _nullable_clamp(_nullable_mul(_nullable_mul(_nullable_float(exchange.get('market_access_index', 0.0)), _nullable_sub(1.0, _nullable_mul(rationing, 0.72))), _nullable_sub(1.0, _nullable_mul(price_adjustment, 0.18))))
        order_ids: list[int] = []
        producer_supply = 0.0
        consumer_demand = 0.0
        price_floor_sum = 0.0
        price_ceiling_sum = 0.0
        producer_count = 0
        consumer_count = 0
        source_firms, firm_available = _selected_source_firms(payload, region_from, region_to, firms_by_region)
        if not firm_available:
            producer_supply = None
            price_floor_sum = None
        for firm in source_firms:
            firm_id = int(firm.get('id', _nullable_neg(1)))
            productivity = _nullable_clamp(_nullable_float(firm.get('productivity_index', 0.0)))
            dependency = _nullable_clamp(_nullable_float(firm.get('market_dependency_index', 0.0)))
            supply_risk = _nullable_clamp(_nullable_float(firm.get('supply_chain_risk_index', 0.0)))
            volume = _nullable_max(0.0, _nullable_div(_nullable_mul(_nullable_mul(requested, _nullable_add(0.2, _nullable_mul(productivity, 0.2))), _nullable_sub(1.0, _nullable_mul(supply_risk, 0.35))), _nullable_max(1, len(source_firms))))
            price_limit = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(0.26, _nullable_mul(dependency, 0.2)), _nullable_mul(supply_risk, 0.28)), _nullable_mul(_nullable_float(exchange.get('price_spread_index', 0.0)), 0.26)))
            fulfillment = _nullable_clamp(_nullable_add(_nullable_mul(clearance_fraction, _nullable_sub(1.0, _nullable_mul(supply_risk, 0.28))), _nullable_mul(productivity, 0.16)))
            order_id = len(orders)
            orders.append({'id': order_id, 'market_exchange_id': exchange_id, 'market_clearing_record_id': len(clearing_records), 'agent_type': 'firm', 'agent_id': firm_id, 'region_id': region_from, 'order_side': 'supply', 'order_kind': ORDER_KIND_BY_SECTOR.get(str(firm.get('sector', '')), 'producer_supply'), 'primary_good': str(exchange.get('primary_good', 'mixed_goods')), 'requested_volume_index': _nullable_round(volume, 6), 'cleared_volume_index': _nullable_round(_nullable_mul(volume, fulfillment), 6), 'limit_price_index': _nullable_round(price_limit, 6), 'price_acceptance_index': _nullable_round(_nullable_clamp(_nullable_add(_nullable_sub(1.0, _nullable_mul(price_limit, 0.36)), _nullable_mul(producer_surplus, 0.16))), 6), 'rationing_index': _nullable_round(_nullable_clamp(_nullable_sub(1.0, fulfillment)), 6), 'inventory_change_index': _nullable_round(_nullable_clamp(_nullable_div(_nullable_mul(volume, _nullable_sub(1.0, fulfillment)), _nullable_max(1.0, requested))), 6)})
            order_ids.append(order_id)
            producer_supply = _nullable_add(producer_supply, volume)
            price_floor_sum = _nullable_add(price_floor_sum, price_limit)
            producer_count = _nullable_add(producer_count, 1)
            producer_order_count = _nullable_add(producer_order_count, 1)
        target_households = households_by_region.get(region_to, [])[:3]
        if not target_households:
            target_households = households_by_region.get(region_from, [])[:1]
        for cohort in target_households:
            cohort_id = int(cohort.get('id', _nullable_neg(1)))
            consumption = _nullable_clamp(_nullable_float(cohort.get('consumption_pressure_index', 0.0)))
            vulnerability = _nullable_clamp(_nullable_float(cohort.get('vulnerability_index', 0.0)))
            income = _nullable_clamp(_nullable_float(cohort.get('income_index', 0.0)))
            volume = _nullable_max(0.0, _nullable_div(_nullable_mul(requested, _nullable_add(_nullable_add(0.22, _nullable_mul(consumption, 0.24)), _nullable_mul(vulnerability, 0.1))), _nullable_max(1, len(target_households))))
            price_limit = _nullable_clamp(_nullable_add(_nullable_sub(_nullable_add(0.44, _nullable_mul(income, 0.24)), _nullable_mul(vulnerability, 0.1)), _nullable_mul(_nullable_float(exchange.get('market_access_index', 0.0)), 0.18)))
            fulfillment = _nullable_clamp(_nullable_add(_nullable_mul(clearance_fraction, _nullable_sub(1.0, _nullable_mul(rationing, 0.28))), _nullable_mul(income, 0.1)))
            order_id = len(orders)
            orders.append({'id': order_id, 'market_exchange_id': exchange_id, 'market_clearing_record_id': len(clearing_records), 'agent_type': 'household_cohort', 'agent_id': cohort_id, 'region_id': region_to, 'order_side': 'demand', 'order_kind': 'consumer_demand', 'primary_good': str(exchange.get('primary_good', 'mixed_goods')), 'requested_volume_index': _nullable_round(volume, 6), 'cleared_volume_index': _nullable_round(_nullable_mul(volume, fulfillment), 6), 'limit_price_index': _nullable_round(price_limit, 6), 'price_acceptance_index': _nullable_round(_nullable_clamp(_nullable_add(_nullable_mul(price_limit, 0.52), _nullable_mul(consumer_welfare, 0.22))), 6), 'rationing_index': _nullable_round(_nullable_clamp(_nullable_sub(1.0, fulfillment)), 6), 'inventory_change_index': _nullable_round(_nullable_neg(_nullable_clamp(_nullable_div(_nullable_mul(volume, _nullable_sub(1.0, fulfillment)), _nullable_max(1.0, requested)))), 6)})
            order_ids.append(order_id)
            consumer_demand = _nullable_add(consumer_demand, volume)
            price_ceiling_sum = _nullable_add(price_ceiling_sum, price_limit)
            consumer_count = _nullable_add(consumer_count, 1)
            consumer_order_count = _nullable_add(consumer_order_count, 1)
        tax_order_volume = _nullable_max(0.0, _nullable_mul(_nullable_mul(requested, _nullable_float(exchange.get('tax_revenue_index', 0.0))), 0.08))
        state_available = tax_order_volume is not None
        if not state_available:
            consumer_demand = None
            price_ceiling_sum = None
        if state_available and tax_order_volume > 0.0:
            order_id = len(orders)
            orders.append({'id': order_id, 'market_exchange_id': exchange_id, 'market_clearing_record_id': len(clearing_records), 'agent_type': 'state', 'agent_id': region_to, 'region_id': region_to, 'order_side': 'demand', 'order_kind': 'tax_collection', 'primary_good': str(exchange.get('primary_good', 'mixed_goods')), 'requested_volume_index': _nullable_round(tax_order_volume, 6), 'cleared_volume_index': _nullable_round(_nullable_mul(tax_order_volume, clearance_fraction), 6), 'limit_price_index': _nullable_round(_nullable_clamp(_nullable_add(0.42, _nullable_mul(price_adjustment, 0.24))), 6), 'price_acceptance_index': _nullable_round(_nullable_clamp(_nullable_add(0.5, _nullable_mul(clearance_fraction, 0.24))), 6), 'rationing_index': _nullable_round(rationing, 6), 'inventory_change_index': 0.0})
            order_ids.append(order_id)
            consumer_demand = _nullable_add(consumer_demand, tax_order_volume)
            price_ceiling_sum = _nullable_add(price_ceiling_sum, _nullable_clamp(_nullable_add(0.42, _nullable_mul(price_adjustment, 0.24))))
            consumer_count = _nullable_add(consumer_count, 1)
            consumer_order_count = _nullable_add(consumer_order_count, 1)
        endogenous_supply = None if producer_supply is None else producer_supply if producer_supply > 0.0 else _nullable_mul(requested, _nullable_float(exchange.get('supply_index', 0.0)))
        endogenous_demand = None if consumer_demand is None else consumer_demand if consumer_demand > 0.0 else _nullable_mul(requested, _nullable_float(exchange.get('demand_index', 0.0)))
        equilibrium_price = _nullable_clamp(_nullable_add(_nullable_add(_nullable_mul(_nullable_div(price_floor_sum, _nullable_max(1, producer_count)), 0.36), _nullable_mul(_nullable_div(price_ceiling_sum, _nullable_max(1, consumer_count)), 0.38)), _nullable_mul(price_adjustment, 0.26)))
        residual = _nullable_clamp(_nullable_div(_nullable_abs(_nullable_sub(endogenous_demand, endogenous_supply)), _nullable_max(1.0, _nullable_add(endogenous_demand, endogenous_supply))))
        price_iteration_ids: list[int] = []
        for iteration_index in range(3):
            progress = _nullable_div(_nullable_add(iteration_index, 1), 3.0)
            iteration_price = _nullable_clamp(_nullable_add(_nullable_mul(equilibrium_price, progress), _nullable_mul(_nullable_float(exchange.get('price_spread_index', 0.0)), _nullable_sub(1.0, progress))))
            supply_volume = _nullable_mul(endogenous_supply, _nullable_clamp(_nullable_add(_nullable_add(0.72, _nullable_mul(iteration_price, 0.18)), _nullable_mul(progress, 0.1))))
            demand_volume = _nullable_mul(endogenous_demand, _nullable_clamp(_nullable_add(_nullable_sub(_nullable_sub(1.02, _nullable_mul(iteration_price, 0.16)), _nullable_mul(rationing, 0.12)), _nullable_mul(progress, 0.04))))
            imbalance = _nullable_sub(demand_volume, supply_volume)
            iteration_id = len(price_iterations)
            price_iterations.append({'id': iteration_id, 'market_exchange_id': exchange_id, 'market_clearing_record_id': len(clearing_records), 'iteration_index': _nullable_add(iteration_index, 1), 'order_ids': list(order_ids), 'order_count': len(order_ids), 'price_index': _nullable_round(iteration_price, 6), 'supply_volume_index': _nullable_round(supply_volume, 6), 'demand_volume_index': _nullable_round(demand_volume, 6), 'imbalance_index': _nullable_round(imbalance, 6), 'excess_demand_index': _nullable_round(_nullable_clamp(_nullable_div(_nullable_max(0.0, imbalance), _nullable_max(1.0, demand_volume))), 6), 'price_adjustment_index': _nullable_round(_nullable_clamp(_nullable_add(_nullable_div(_nullable_abs(imbalance), _nullable_max(1.0, _nullable_add(demand_volume, supply_volume))), _nullable_mul(price_adjustment, 0.24))), 6)})
            price_iteration_ids.append(iteration_id)
        inventory_history_id = len(inventory_histories)
        net_inventory_delta = _nullable_sum((_nullable_float(orders[order_id].get('inventory_change_index', 0.0)) for order_id in order_ids if 0 <= order_id < len(orders)))
        initial_inventory = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(_nullable_float(exchange.get('supply_index', 0.0)), 0.28), _nullable_mul(clearance_fraction, 0.24)), _nullable_mul(_nullable_sub(1.0, rationing), 0.18)), _nullable_mul(utilization, 0.16)), _nullable_mul(producer_surplus, 0.14)))
        target_inventory = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_add(0.26, _nullable_mul(_nullable_float(exchange.get('demand_index', 0.0)), 0.22)), _nullable_mul(_nullable_float(exchange.get('market_access_index', 0.0)), 0.16)), _nullable_mul(_nullable_sub(1.0, rationing), 0.16)), _nullable_mul(consumer_welfare, 0.2)))
        producer_expectation_base = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(producer_surplus, 0.35), _nullable_mul(_nullable_sub(1.0, rationing), 0.25)), _nullable_mul(_nullable_sub(1.0, price_adjustment), 0.2)), _nullable_mul(clearance_fraction, 0.2)))
        consumer_expectation_base = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(consumer_welfare, 0.38), _nullable_mul(_nullable_sub(1.0, rationing), 0.3)), _nullable_mul(_nullable_float(exchange.get('market_access_index', 0.0)), 0.2)), _nullable_mul(_nullable_sub(1.0, price_adjustment), 0.12)))
        inventory = initial_inventory
        inventory_steps: list[dict[str, Any]] = []
        pressure_sum = 0.0
        price_expectation_sum = 0.0
        supply_response_sum = 0.0
        demand_adjustment_sum = 0.0
        learning_sum = 0.0
        for sequence_index, iteration_id in enumerate(price_iteration_ids):
            iteration = price_iterations[iteration_id]
            price_index = _nullable_clamp(_nullable_float(iteration.get('price_index', 0.0)))
            learning_rate = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_add(0.16, _nullable_mul(price_adjustment, 0.24)), _nullable_mul(residual, 0.22)), _nullable_mul(rationing, 0.2)), _nullable_mul(_nullable_abs(net_inventory_delta), 0.18)))
            current_gap = _nullable_abs(_nullable_sub(inventory, target_inventory))
            producer_expectation = _nullable_clamp(_nullable_add(_nullable_mul(producer_expectation_base, _nullable_sub(1.0, _nullable_mul(learning_rate, 0.24))), _nullable_mul(_nullable_mul(_nullable_clamp(_nullable_div(_nullable_float(iteration.get('supply_volume_index', 0.0)), _nullable_max(1.0, endogenous_supply))), learning_rate), 0.24)))
            consumer_expectation = _nullable_clamp(_nullable_add(_nullable_mul(consumer_expectation_base, _nullable_sub(1.0, _nullable_mul(learning_rate, 0.24))), _nullable_mul(_nullable_mul(_nullable_clamp(_nullable_div(_nullable_float(iteration.get('demand_volume_index', 0.0)), _nullable_max(1.0, endogenous_demand))), learning_rate), 0.24)))
            supply_response = _nullable_clamp(_nullable_add(_nullable_add(_nullable_mul(_nullable_clamp(_nullable_div(_nullable_float(iteration.get('supply_volume_index', 0.0)), _nullable_max(1.0, endogenous_supply))), 0.52), _nullable_mul(producer_expectation, 0.28)), _nullable_mul(_nullable_sub(1.0, current_gap), 0.2)))
            demand_adjustment = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(rationing, 0.28), _nullable_mul(price_index, 0.22)), _nullable_mul(_nullable_sub(1.0, clearance_fraction), 0.18)), _nullable_mul(_nullable_clamp(_nullable_div(_nullable_float(iteration.get('demand_volume_index', 0.0)), _nullable_max(1.0, endogenous_demand))), 0.16)), _nullable_mul(consumer_expectation, 0.16)))
            inventory = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(inventory, _nullable_mul(_nullable_mul(_nullable_sub(target_inventory, inventory), learning_rate), 0.35)), _nullable_mul(net_inventory_delta, 0.28)), _nullable_mul(_nullable_sub(supply_response, demand_adjustment), 0.08)))
            inventory_gap = _nullable_abs(_nullable_sub(inventory, target_inventory))
            inventory_pressure = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(inventory_gap, 0.45), _nullable_mul(rationing, 0.22)), _nullable_mul(residual, 0.18)), _nullable_mul(price_index, 0.15)))
            price_expectation = _nullable_clamp(_nullable_add(_nullable_mul(producer_expectation, 0.48), _nullable_mul(consumer_expectation, 0.52)))
            inventory_steps.append({'sequence_index': sequence_index, 'price_iteration_id': iteration_id, 'price_index': _nullable_round(price_index, 6), 'inventory_index': _nullable_round(inventory, 6), 'target_inventory_index': _nullable_round(target_inventory, 6), 'inventory_gap_index': _nullable_round(inventory_gap, 6), 'supply_response_index': _nullable_round(supply_response, 6), 'demand_adjustment_index': _nullable_round(demand_adjustment, 6), 'learning_rate_index': _nullable_round(learning_rate, 6), 'producer_expectation_index': _nullable_round(producer_expectation, 6), 'consumer_expectation_index': _nullable_round(consumer_expectation, 6), 'rationing_memory_index': _nullable_round(rationing, 6), 'clearance_memory_index': _nullable_round(clearance_fraction, 6)})
            pressure_sum = _nullable_add(pressure_sum, inventory_pressure)
            price_expectation_sum = _nullable_add(price_expectation_sum, price_expectation)
            supply_response_sum = _nullable_add(supply_response_sum, supply_response)
            demand_adjustment_sum = _nullable_add(demand_adjustment_sum, demand_adjustment)
            learning_sum = _nullable_add(learning_sum, learning_rate)
        step_divisor = _nullable_max(1, len(inventory_steps))
        final_inventory = inventory_steps[_nullable_neg(1)]['inventory_index'] if inventory_steps else _nullable_round(initial_inventory, 6)
        final_gap = _nullable_abs(_nullable_sub(_nullable_float(final_inventory), target_inventory))
        mean_pressure = _nullable_div(pressure_sum, step_divisor) if inventory_steps else 0.0
        high_stress = None if mean_pressure is None or final_gap is None else bool(mean_pressure >= 0.6 or final_gap >= 0.45)
        inventory_histories.append({'id': inventory_history_id, 'market_clearing_record_id': len(clearing_records), 'market_exchange_id': exchange_id, 'trade_flow_id': int(exchange.get('trade_flow_id', _nullable_neg(1))), 'route_id': route_id, 'region_from': region_from, 'region_to': region_to, 'primary_good': str(exchange.get('primary_good', 'mixed_goods')), 'initial_inventory_index': _nullable_round(initial_inventory, 6), 'target_inventory_index': _nullable_round(target_inventory, 6), 'final_inventory_index': _nullable_round(_nullable_float(final_inventory), 6), 'inventory_gap_index': _nullable_round(final_gap, 6), 'learning_rate_index': _nullable_round(_nullable_div(learning_sum, step_divisor), 6) if inventory_steps else 0.0, 'mean_inventory_pressure_index': _nullable_round(mean_pressure, 6), 'mean_price_expectation_index': _nullable_round(_nullable_div(price_expectation_sum, step_divisor), 6) if inventory_steps else 0.0, 'mean_supply_response_index': _nullable_round(_nullable_div(supply_response_sum, step_divisor), 6) if inventory_steps else 0.0, 'mean_demand_adjustment_index': _nullable_round(_nullable_div(demand_adjustment_sum, step_divisor), 6) if inventory_steps else 0.0, 'high_inventory_stress': high_stress, 'step_count': len(inventory_steps), 'steps': inventory_steps})
        inventory_step_count = _nullable_add(inventory_step_count, len(inventory_steps))
        inventory_gap_sum = _nullable_add(inventory_gap_sum, final_gap)
        inventory_learning_sum = _nullable_add(inventory_learning_sum, _nullable_div(learning_sum, step_divisor) if inventory_steps else 0.0)
        inventory_pressure_sum = _nullable_add(inventory_pressure_sum, mean_pressure)
        high_inventory_stress_count = _nullable_add(high_inventory_stress_count, None if high_stress is None else int(high_stress))
        record = {'id': len(clearing_records), 'market_exchange_id': exchange_id, 'trade_flow_id': int(exchange.get('trade_flow_id', _nullable_neg(1))), 'route_id': route_id, 'route_capacity_constraint_id': int(constraint.get('id', _nullable_neg(1))), 'region_from': region_from, 'region_to': region_to, 'primary_good': str(exchange.get('primary_good', 'mixed_goods')), 'requested_volume_index': _nullable_round(requested, 6), 'cleared_volume_index': _nullable_round(cleared, 6), 'unmet_demand_index': _nullable_round(unmet, 6), 'clearance_fraction': _nullable_round(clearance_fraction, 6), 'route_utilization_index': _nullable_round(utilization, 6), 'price_adjustment_index': _nullable_round(price_adjustment, 6), 'rationing_index': _nullable_round(rationing, 6), 'producer_surplus_index': _nullable_round(producer_surplus, 6), 'consumer_welfare_index': _nullable_round(consumer_welfare, 6), 'agent_order_ids': order_ids, 'agent_order_count': len(order_ids), 'price_iteration_ids': price_iteration_ids, 'price_iteration_count': len(price_iteration_ids), 'market_inventory_history_id': inventory_history_id, 'endogenous_supply_index': _nullable_round(endogenous_supply, 6), 'endogenous_demand_index': _nullable_round(endogenous_demand, 6), 'equilibrium_price_index': _nullable_round(equilibrium_price, 6), 'price_residual_index': _nullable_round(residual, 6)}
        record['order_family_availability'] = {'firm': firm_available, 'household': True, 'state': state_available}
        record['agent_order_selection_complete'] = firm_available and state_available
        exchange['market_clearing_record_id'] = record['id']
        exchange['cleared_volume_index'] = record['cleared_volume_index']
        exchange['unmet_demand_index'] = record['unmet_demand_index']
        exchange['clearance_fraction'] = record['clearance_fraction']
        exchange['market_inventory_history_id'] = inventory_history_id
        clearing_records.append(record)
        price_adjustment_sum = _nullable_add(price_adjustment_sum, price_adjustment)
        rationing_sum = _nullable_add(rationing_sum, rationing)
        clearance_fraction_sum = _nullable_add(clearance_fraction_sum, clearance_fraction)
        constrained_records = _nullable_add(constrained_records, None if record['unmet_demand_index'] is None else int(_nullable_float(record['unmet_demand_index']) > 0.0))
        endogenous_supply_sum = _nullable_add(endogenous_supply_sum, endogenous_supply)
        endogenous_demand_sum = _nullable_add(endogenous_demand_sum, endogenous_demand)
        price_iteration_residual_sum = _nullable_add(price_iteration_residual_sum, residual)
    route_constraint_count = len(constraints)
    clearing_count = len(clearing_records)
    inventory_count = len(inventory_histories)
    summary = {'route_capacity_constraint_count': route_constraint_count, 'market_clearing_record_count': clearing_count, 'market_agent_order_count': len(orders), 'market_price_iteration_count': len(price_iterations), 'market_inventory_history_count': inventory_count, 'market_inventory_step_count': inventory_step_count, 'producer_market_order_count': producer_order_count, 'consumer_market_order_count': consumer_order_count, 'constrained_market_exchange_count': constrained_records, 'total_market_requested_volume_index': _nullable_round(total_requested_volume, 6), 'total_market_cleared_volume_index': _nullable_round(total_cleared_volume, 6), 'total_market_unmet_demand_index': _nullable_round(total_unmet_volume, 6), 'total_endogenous_market_supply_index': _nullable_round(endogenous_supply_sum, 6), 'total_endogenous_market_demand_index': _nullable_round(endogenous_demand_sum, 6), 'mean_market_clearance_fraction': _nullable_round(_nullable_div(clearance_fraction_sum, clearing_count), 6) if clearing_count else 0.0, 'mean_route_capacity_utilization_index': _nullable_round(_nullable_div(route_utilization_sum, route_constraint_count), 6) if route_constraint_count else 0.0, 'mean_market_price_adjustment_index': _nullable_round(_nullable_div(price_adjustment_sum, clearing_count), 6) if clearing_count else 0.0, 'mean_market_rationing_index': _nullable_round(_nullable_div(rationing_sum, clearing_count), 6) if clearing_count else 0.0, 'mean_market_equilibrium_residual_index': _nullable_round(_nullable_div(price_iteration_residual_sum, clearing_count), 6) if clearing_count else 0.0, 'mean_market_inventory_gap_index': _nullable_round(_nullable_div(inventory_gap_sum, inventory_count), 6) if inventory_count else 0.0, 'mean_market_learning_rate_index': _nullable_round(_nullable_div(inventory_learning_sum, inventory_count), 6) if inventory_count else 0.0, 'mean_market_inventory_pressure_index': _nullable_round(_nullable_div(inventory_pressure_sum, inventory_count), 6) if inventory_count else 0.0, 'high_inventory_stress_market_count': high_inventory_stress_count}
    route_annotation_keys = ('route_capacity_constraint_id', 'market_capacity_volume_index', 'market_capacity_utilization_index')
    exchange_annotation_keys = ('market_clearing_record_id', 'cleared_volume_index', 'unmet_demand_index', 'clearance_fraction', 'market_inventory_history_id')
    route_annotations = {int(route.get('id', _nullable_neg(1))): {key: route[key] for key in route_annotation_keys if key in route} for route in routes if int(route.get('id', _nullable_neg(1))) >= 0}
    exchange_annotations = {int(exchange.get('id', _nullable_neg(1))): {key: exchange[key] for key in exchange_annotation_keys if key in exchange} for exchange in exchanges if int(exchange.get('id', _nullable_neg(1))) >= 0}
    return (constraints, clearing_records, orders, price_iterations, inventory_histories, route_annotations, exchange_annotations, summary)

FIELD_SCHEMAS={
 "route_capacity_constraints":("distance_km","requested_volume_index","capacity_volume_index","cleared_volume_index","unmet_volume_index","utilization_index","congestion_index","shortage_index","spoilage_loss_index"),
 "market_clearing_records":("requested_volume_index","cleared_volume_index","unmet_demand_index","clearance_fraction","route_utilization_index","price_adjustment_index","rationing_index","producer_surplus_index","consumer_welfare_index","endogenous_supply_index","endogenous_demand_index","equilibrium_price_index","price_residual_index"),
 "market_agent_orders":("requested_volume_index","cleared_volume_index","limit_price_index","price_acceptance_index","rationing_index","inventory_change_index"),
 "market_price_iterations":("price_index","supply_volume_index","demand_volume_index","imbalance_index","excess_demand_index","price_adjustment_index"),
 "market_inventory_histories":("initial_inventory_index","target_inventory_index","final_inventory_index","inventory_gap_index","learning_rate_index","mean_inventory_pressure_index","mean_price_expectation_index","mean_supply_response_index","mean_demand_adjustment_index","high_inventory_stress")}
INVENTORY_STEP_FIELDS=("price_index","inventory_index","target_inventory_index","inventory_gap_index","supply_response_index","demand_adjustment_index","learning_rate_index","producer_expectation_index","consumer_expectation_index","rationing_memory_index","clearance_memory_index")
SUMMARY_ESTIMATES=("constrained_market_exchange_count","total_market_requested_volume_index","total_market_cleared_volume_index","total_market_unmet_demand_index","total_endogenous_market_supply_index","total_endogenous_market_demand_index","mean_market_clearance_fraction","mean_route_capacity_utilization_index","mean_market_price_adjustment_index","mean_market_rationing_index","mean_market_equilibrium_residual_index","mean_market_inventory_gap_index","mean_market_learning_rate_index","mean_market_inventory_pressure_index","high_inventory_stress_market_count")
SUMMARY_FIELDS=(*SUMMARY_ESTIMATES,"market_clearing_model","route_capacity_constraint_count","market_clearing_record_count","market_agent_order_count","market_price_iteration_count","market_inventory_history_count","market_inventory_step_count","producer_market_order_count","consumer_market_order_count","market_summary_estimate_availability","market_order_selection_complete","unavailable_market_order_exchange_ids")
ROUTE_ANNOTATIONS=("route_capacity_constraint_id","market_capacity_volume_index","market_capacity_utilization_index","market_capacity_estimate_availability")
EXCHANGE_ANNOTATIONS=("market_clearing_record_id","cleared_volume_index","unmet_demand_index","clearance_fraction","market_inventory_history_id","market_clearing_estimate_availability")


def market_model_v2():
    from .market_clearing_validation import _market_clearing_model
    return {**_market_clearing_model(),"model_type":"causal_route_capacity_agent_orders_price_iteration_inventory_learning_market_clearing_v2",
        "source_demographic_agent_model":"causal_population_economy_logistics_household_firm_demographic_history_v2",
        "source_logistics_exchange_model":"causal_region_route_trade_economy_logistics_exchange_v2",
        "availability_policy":"actual_route_exchange_slots_nullable_estimates_without_unknown_positive_sum_fallback",
        "order_selection_policy":"complete_firm_first_three_or_fallback_and_known_state_tax_presence_with_explicit_family_coverage",
        "aggregate_policy":"complete_nullable_estimates_or_null_emitted_order_counts_not_inferred_complete_selection",
        "annotation_model":"separate_owned_market_availability_maps_preserving_parent_estimate_maps_v2"}


def _exact(a,b):
    if type(a) is not type(b):return False
    if type(b) is dict:return a.keys()==b.keys() and all(_exact(a[k],v) for k,v in b.items())
    if type(b) is list:return len(a)==len(b) and all(_exact(x,y) for x,y in zip(a,b))
    return a==b


def market_version(world):
    from .native_social_availability import uses_native_social_availability
    from .market_clearing_validation import _market_clearing_model
    if type(world) is not dict or type(world.get("summary",{})) is not dict:raise ValueError("market world/summary object required")
    own=None
    if "market_clearing_model" in world:
        own=1 if _exact(world["market_clearing_model"],_market_clearing_model()) else 2 if _exact(world["market_clearing_model"],market_model_v2()) else None
        if own is None:raise ValueError("unknown own market-clearing model")
        if not _exact(world.get("summary",{}).get("market_clearing_model"),world["market_clearing_model"]["model_type"]):raise ValueError("market own summary identity mismatch")
    native=uses_native_social_availability(world)
    if own is not None and (own==2)!=native:raise ValueError("market native family mismatch; explicit upgrade required")
    version=own or (2 if native else 1)
    if version==2 and own is None:
        if (any(k in world for k in FIELD_SCHEMAS) or any(k in world["summary"] for k in SUMMARY_FIELDS)
            or any(any(k in r for k in ROUTE_ANNOTATIONS) for r in world["routes"])
            or any(any(k in r for k in EXCHANGE_ANNOTATIONS) for r in world["market_exchanges"])):
            raise ValueError("undeclared market outputs require complete audited clearing")
    if version==1:
        if (any(k in world.get("summary",{}) for k in ("market_summary_estimate_availability","market_order_selection_complete","unavailable_market_order_exchange_ids"))
            or any(type(r) is dict and any(field in r for field in ("estimate_availability","order_family_availability","agent_order_selection_complete"))
                for k in FIELD_SCHEMAS for r in world.get(k,[]))
            or any(type(r) is dict and "market_capacity_estimate_availability" in r for r in world.get("routes",[]))
            or any(type(r) is dict and "market_clearing_estimate_availability" in r for r in world.get("market_exchanges",[]))
            or any(type(step) is dict and "estimate_availability" in step
                for r in world.get("market_inventory_histories",[]) if type(r) is dict
                for step in r.get("steps",[]))):
            raise ValueError("market availability mirrors require successor model")
    return version


def require_market_sources(world):
    from .demographic_availability_validation import validate_demographic_availability
    if validate_demographic_availability(world):raise ValueError("independent demographic2 source replay required")


def expected_market_availability(world):
    constraints,clearing,orders,prices,inventories,routes,exchanges,summary=_replay_market_numeric(world)
    result=dict(zip(FIELD_SCHEMAS,(constraints,clearing,orders,prices,inventories),strict=True))
    for key,fields in FIELD_SCHEMAS.items():
        for row in result[key]:row["estimate_availability"]={k:row[k] is not None for k in fields}
    for record in inventories:
        for step in record["steps"]:step["estimate_availability"]={k:step[k] is not None for k in INVENTORY_STEP_FIELDS}
    for annotations in routes.values():
        if "market_capacity_volume_index" in annotations:
            annotations["market_capacity_estimate_availability"]={k:annotations[k] is not None for k in ("market_capacity_volume_index","market_capacity_utilization_index")}
    for annotations in exchanges.values():
        annotations["market_clearing_estimate_availability"]={k:annotations[k] is not None for k in ("cleared_volume_index","unmet_demand_index","clearance_fraction")}
    unavailable=[r["market_exchange_id"] for r in clearing if not r["agent_order_selection_complete"]]
    summary.update({"market_summary_estimate_availability":{k:summary[k] is not None for k in SUMMARY_ESTIMATES},
        "market_order_selection_complete":not unavailable,"unavailable_market_order_exchange_ids":unavailable})
    return {**result,"route_annotations":routes,"exchange_annotations":exchanges,"summary":summary}


def _projection(a,b):
    return type(a) is dict and all(k in a and _exact(a[k],v) for k,v in b.items())


def validate_market_availability(world):
    try:
        if market_version(world)!=2 or "market_clearing_model" not in world:raise ValueError("explicit market2 required")
        require_market_sources(world)
        expected=expected_market_availability(world)
        for key in FIELD_SCHEMAS:
            rows=world.get(key);wanted=expected[key]
            if type(rows) is not list or len(rows)!=len(wanted) or not all(_projection(a,b) for a,b in zip(rows,wanted)):raise ValueError("market nullable records disagree")
        if not _projection(world["summary"],expected["summary"]):raise ValueError("market summary disagreement")
        for table,fields,name in (("routes",ROUTE_ANNOTATIONS,"route_annotations"),("market_exchanges",EXCHANGE_ANNOTATIONS,"exchange_annotations")):
            for row in world[table]:
                owned={k:row[k] for k in fields if k in row}
                if not _exact(owned,expected[name][row["id"]]):raise ValueError("market source annotation disagreement")
        return []
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,ZeroDivisionError,AttributeError):
        return ["market-clearing availability or independent replay invalid"]
