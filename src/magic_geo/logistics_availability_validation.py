"""Independent nullable logistics replay derived from the historical oracle."""
from __future__ import annotations
from typing import Any
from .native_social_availability import finite_number
from .logistics_exchange_validation import (
    _clamp, _economy_by_region, _final_step, _settlement_regions,
    _route_regions, _trade_regions, _index_records,
)

NETWORK_ESTIMATES = (
    "total_route_distance_km", "total_route_cost", "total_trade_volume_index",
    "interregional_trade_volume_index", "army_capacity_population", "supply_capacity_index",
    "transport_efficiency_index", "logistics_resilience_index", "chokepoint_exposure_index",
)
EXCHANGE_ESTIMATES = (
    "distance_km", "volume_index", "friction", "supply_index", "demand_index",
    "price_spread_index", "market_access_index", "tax_revenue_index",
    "food_security_link_index", "disruption_risk_index",
)

OWNED_COLLECTIONS = (
    "logistics_networks", "market_exchanges", "campaign_movements", "campaign_path_segments",
    "campaign_front_histories", "tactical_engagements", "strategic_campaign_plans",
    "campaign_operations_availability",
)


def _owned_summary_key(key):
    return key.startswith((
        "logistics_", "mean_logistics_", "market_exchange_", "mean_market_access_",
        "mean_market_disruption_", "total_market_exchange_", "interregional_market_exchange_",
        "campaign_", "recorded_campaign_", "mean_campaign_", "total_campaign_",
        "tactical_", "mean_tactical_", "recorded_tactical_", "high_pressure_tactical_",
        "strategic_", "mean_strategic_", "recorded_strategic_", "high_escalation_strategic_",
        "independent_counter_campaign_", "mean_counter_campaign_", "high_attrition_campaign_",
    ))


def uses_logistics_availability(world):
    from .native_social_availability import uses_native_social_availability, exact_contract
    native = uses_native_social_availability(world)
    summary = world.get("summary", {})
    if type(summary) is not dict:
        raise ValueError("typed logistics summary required")
    own = [key in world for key in ("logistics_exchange_model", "campaign_operations_model")]
    if native and any(own) and not all(own):
        raise ValueError("complete matched logistics/campaign declarations required")
    if any(own):
        from .logistics_exchange_validation import _logistics_exchange_model
        from .campaign_operations_validation import _campaign_operations_model
        expected = (logistics_model_v2(), campaign_model_v2()) if native else (_logistics_exchange_model(), _campaign_operations_model())
        for key, model in zip(("logistics_exchange_model", "campaign_operations_model"), expected):
            if key not in world:
                continue
            if not exact_contract(world[key], model) or summary.get(key) != model["model_type"]:
                raise ValueError("incompatible logistics model or parent family")
    elif native:
        if any(key in world for key in OWNED_COLLECTIONS) or any(_owned_summary_key(key) for key in summary):
            raise ValueError("undeclared logistics output requires complete audited clearing")
        if any(any(key in row for key in ("campaign_movement_id", "tactical_engagement_id", "strategic_campaign_plan_id", "campaign_link_availability")) for row in world["conflicts"]):
            raise ValueError("undeclared campaign links require complete audited clearing")
    if not native:
        if ("campaign_operations_availability" in world or "logistics_summary_availability" in summary or "campaign_summary_availability" in summary
                or any(type(row) is dict and any(key in row for key in ("estimate_availability", "operations_estimate_available", "campaign_front_history_available"))
                       for collection in OWNED_COLLECTIONS[:-1] for row in (world.get(collection) if type(world.get(collection)) is list else []))
                or any("campaign_link_availability" in row for row in (world.get("conflicts") if type(world.get("conflicts")) is list else []) if type(row) is dict)):
            raise ValueError("orphan logistics availability cannot enter historical replay")
    return native


def logistics_model_v2():
    from .logistics_exchange_validation import _logistics_exchange_model
    return {
        **_logistics_exchange_model(),
        "model_type": "causal_region_route_trade_economy_logistics_exchange_v2",
        "source_economy_history_model": "causal_population_trade_conflict_treasury_economy_history_v2",
        "source_conflict_model": "causal_border_pair_pressure_trade_conflict_selection_v2",
        "source_route_network_model": "causal_endpoint_barrier_ranked_route_network_v1",
        "source_trade_flow_model": "causal_route_endpoint_complement_trade_flows_v1",
        "availability_policy": "retain_every_region_and_trade_null_only_dependent_economic_or_conflict_estimates",
        "summary_policy": "complete_source_scope_serialized_record_statistics_conditional_empty_zero",
    }


def campaign_model_v2():
    from .campaign_operations_validation import _campaign_operations_model
    return {
        **_campaign_operations_model(),
        "model_type": "causal_conflict_cell_path_front_tactical_strategic_campaign_operations_v2",
        "source_logistics_exchange_model": "causal_region_route_trade_economy_logistics_exchange_v2",
        "source_conflict_model": "causal_border_pair_pressure_trade_conflict_selection_v2",
        "source_route_network_model": "causal_endpoint_barrier_ranked_route_network_v1",
        "availability_policy": "preserve_actual_conflict_paths_and_forces_null_unavailable_operations_with_separate_family_coverage",
        "summary_policy": "complete_source_scope_serialized_record_statistics_conditional_empty_zero",
    }


def require_logistics_sources(world):
    from .history_economy_validation import validate_history_economy_replay
    from .cultural_geography_validation import validate_cultural_geography_replay
    from .native_social_availability import require_native_social_availability
    require_native_social_availability(world)
    for audit in (validate_cultural_geography_replay, validate_history_economy_replay):
        errors = audit(world)
        if errors:
            raise ValueError("invalid logistics parent: " + "; ".join(errors))
    for cell in world["cells"]:
        for key in ("lat_deg", "lon_deg", "elevation_m", "seasonal_aridity_index", "ice_thickness_m"):
            finite_number(cell.get(key))
        for key in ("is_water", "is_river"):
            if type(cell.get(key)) is not bool:
                raise ValueError("typed campaign physical source required")
        for key in ("landform", "biome"):
            if type(cell.get(key)) is not str:
                raise ValueError("explicit campaign physical descriptor required")
    for collection, fields in (
        ("routes", ("distance_km", "cost")),
        ("trade_flows", ("volume_index", "distance_km", "friction")),
        ("borders", ("barrier_score", "length_km")),
    ):
        for row in world[collection]:
            for key in fields:
                if finite_number(row.get(key)) < 0:
                    raise ValueError("nonnegative logistics physical source required")


def _matches(actual, expected, *, exact_keys=True):
    import math
    if type(expected) is dict:
        return (type(actual) is dict and (actual.keys() == expected.keys() if exact_keys else actual.keys() >= expected.keys())
                and all(_matches(actual[key], value) for key, value in expected.items()))
    if type(expected) is list:
        return type(actual) is list and len(actual) == len(expected) and all(_matches(a, b) for a, b in zip(actual, expected))
    if type(expected) is float:
        return type(actual) in (int, float) and math.isfinite(actual) and actual == expected
    return type(actual) is type(expected) and actual == expected


def validate_logistics_availability(world):
    from .native_social_availability import exact_contract
    try:
        require_logistics_sources(world)
        model = logistics_model_v2()
        if not exact_contract(world.get("logistics_exchange_model"), model) or world["summary"].get("logistics_exchange_model") != model["model_type"]:
            raise ValueError("exact logistics model required")
        networks, exchanges, summary = expected_networks_and_exchanges(world)
        for rows, fields in ((networks, NETWORK_ESTIMATES), (exchanges, EXCHANGE_ESTIMATES)):
            for row in rows:
                row["estimate_availability"] = {key: row[key] is not None for key in fields}
        for key, expected in (("logistics_networks", networks), ("market_exchanges", exchanges)):
            actual = world.get(key)
            # Descendant market linkage fields live on these records. Their
            # presence does not alter this parent's exact owned estimate map.
            if (type(actual) is not list or len(actual) != len(expected)
                    or any(not _matches(row, wanted, exact_keys=False) for row, wanted in zip(actual, expected))):
                raise ValueError("logistics estimates disagree with actual sources")
        summary["logistics_summary_availability"] = {key: value is not None for key, value in summary.items()}
        if not _matches(world["summary"], summary, exact_keys=False):
            raise ValueError("logistics summary disagrees with actual source coverage")
        return []
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, ZeroDivisionError):
        return ["logistics exchange availability or causal replay invalid"]


def _conditional(formula, *values):
    if any(value is None for value in values):
        return None
    return formula(*values)


def _estimate(row, field, clamp=False):
    flags=row.get("estimate_availability")
    if type(flags) is not dict or type(flags.get(field)) is not bool or field not in row:
        raise ValueError("exact economy estimate source required")
    if not flags[field]:
        if row[field] is not None:
            raise ValueError("unavailable economy source must be null")
        return None
    value=finite_number(row[field])
    return _clamp(value) if clamp else value


def _expected_pressure(payload):
    available=payload["native_social_availability"]["conflict_inference_available"]
    candidates={row[key] for row in payload["borders"] for key in ("region_a","region_b")}
    pressures={row["id"]: (None if not available and row["id"] in candidates else 0.) for row in payload["political_regions"]}
    for row in payload["conflicts"]:
        pressure=_clamp(.35*_clamp(row["intensity"])+.35*_clamp(row["economic_disruption_index"])+.30*_clamp(row["logistics_strain_index"]))
        for key in ("region_a","region_b"):
            if pressures[row[key]] is None:
                raise ValueError("incomplete global conflict selection")
            pressures[row[key]]=max(pressures[row[key]],pressure)
    return pressures


def expected_networks_and_exchanges(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    regions = payload['political_regions']
    routes = payload['routes']
    trade_flows = payload['trade_flows']
    economies = _economy_by_region(payload)
    settlement_regions = _settlement_regions(payload)
    conflict_pressure = _expected_pressure(payload)
    route_by_id = _index_records(routes)
    trade_by_id = _index_records(trade_flows)
    route_ids_by_region: dict[int, set[int]] = {}
    for route in routes:
        route_id = int(route.get('id', -1))
        if route_id < 0:
            continue
        for region_id in _route_regions(route, settlement_regions):
            route_ids_by_region.setdefault(region_id, set()).add(route_id)
    trade_ids_by_region: dict[int, set[int]] = {}
    for trade in trade_flows:
        trade_id = int(trade.get('id', -1))
        if trade_id < 0:
            continue
        for region_id in _trade_regions(trade):
            trade_ids_by_region.setdefault(region_id, set()).add(trade_id)
    border_ids_by_region: dict[int, set[int]] = {}
    for border in payload['borders']:
        border_id = int(border.get('id', -1))
        if border_id < 0:
            continue
        for key in ('region_a', 'region_b'):
            region_id = int(border.get(key, -1))
            if region_id >= 0:
                border_ids_by_region.setdefault(region_id, set()).add(border_id)
    networks: list[dict[str, Any]] = []
    network_by_region: dict[int, dict[str, Any]] = {}
    total_route_links = 0
    efficiency_sum = 0.0
    resilience_sum = 0.0
    max_route_count = max((len(ids) for ids in route_ids_by_region.values()), default=1)
    for region in sorted(regions, key=lambda item: int(item.get('id', -1))):
        region_id = int(region.get('id', -1))
        if region_id < 0:
            continue
        route_ids = sorted(route_ids_by_region.get(region_id, set()))
        trade_ids = sorted(trade_ids_by_region.get(region_id, set()))
        border_ids = sorted(border_ids_by_region.get(region_id, set()))
        economy = economies.get(region_id, {})
        final_step = _final_step(economy)
        route_distance = sum((float(route_by_id[route_id].get('distance_km', 0.0)) for route_id in route_ids if route_id in route_by_id))
        route_cost = sum((float(route_by_id[route_id].get('cost', 0.0)) for route_id in route_ids if route_id in route_by_id))
        trade_volume = sum((float(trade_by_id[trade_id].get('volume_index', 0.0)) for trade_id in trade_ids if trade_id in trade_by_id))
        interregional_trade = sum((float(trade_by_id[trade_id].get('volume_index', 0.0)) for trade_id in trade_ids if trade_id in trade_by_id and bool(trade_by_id[trade_id].get('interregional', False))))
        route_efficiency = _clamp(route_distance / max(route_cost, 1.0))
        route_density = _clamp(len(route_ids) / max(1, max_route_count))
        transport_efficiency = _clamp(route_efficiency * 0.72 + route_density * 0.28)
        prosperity = _estimate(final_step, 'prosperity_index', clamp=True)
        trade_dependency = _estimate(final_step, 'trade_dependency_index', clamp=True)
        peak_output = _estimate(economy, 'peak_gross_output_index')
        peak_army = _estimate(economy, 'max_army_capacity_population')
        treasury = _estimate(economy, 'peak_treasury_index')
        pressure = conflict_pressure.get(region_id, 0.0)
        supply_capacity = _conditional(lambda peak_output, peak_army, trade_dependency: _clamp(peak_output / 1200.0 * 0.34 + peak_army / 25000000.0 * 0.24 + route_density * 0.24 + trade_dependency * 0.18), peak_output, peak_army, trade_dependency)
        resilience = _conditional(lambda prosperity, treasury, pressure: _clamp(transport_efficiency * 0.34 + prosperity * 0.24 + treasury / 180.0 * 0.18 + (1.0 - pressure) * 0.24), prosperity, treasury, pressure)
        mean_trade_friction = sum((float(trade_by_id[trade_id].get('friction', 0.0)) for trade_id in trade_ids if trade_id in trade_by_id)) / max(1, len(trade_ids))
        chokepoint_exposure = _conditional(lambda pressure: _clamp(mean_trade_friction * 0.36 + len(border_ids) / max(1, len(border_ids) + len(route_ids)) * 0.22 + pressure * 0.42), pressure)
        network = {'id': len(networks), 'region_id': region_id, 'route_ids': route_ids, 'trade_flow_ids': trade_ids, 'border_ids': border_ids, 'route_count': len(route_ids), 'trade_flow_count': len(trade_ids), 'border_count': len(border_ids), 'total_route_distance_km': round(route_distance, 6), 'total_route_cost': round(route_cost, 6), 'total_trade_volume_index': round(trade_volume, 6), 'interregional_trade_volume_index': round(interregional_trade, 6), 'army_capacity_population': _conditional(lambda peak_army: round(peak_army, 6), peak_army), 'supply_capacity_index': _conditional(lambda supply_capacity: round(supply_capacity, 6), supply_capacity), 'transport_efficiency_index': round(transport_efficiency, 6), 'logistics_resilience_index': _conditional(lambda resilience: round(resilience, 6), resilience), 'chokepoint_exposure_index': _conditional(lambda chokepoint_exposure: round(chokepoint_exposure, 6), chokepoint_exposure)}
        networks.append(network)
        network_by_region[region_id] = network
        total_route_links += len(route_ids)
        efficiency_sum += transport_efficiency
        resilience_sum = _conditional(lambda a, b: a + b, resilience_sum, resilience)
    exchanges: list[dict[str, Any]] = []
    market_access_sum = 0.0
    disruption_sum = 0.0
    total_market_volume = 0.0
    interregional_market_count = 0
    for trade in sorted(trade_flows, key=lambda item: int(item.get('id', -1))):
        trade_id = int(trade.get('id', -1))
        route_id = int(trade.get('route_id', -1))
        source_region = int(trade.get('region_from', -1))
        target_region = int(trade.get('region_to', -1))
        route = route_by_id.get(route_id, {})
        source_economy = _final_step(economies.get(source_region, {}))
        target_economy = _final_step(economies.get(target_region, {}))
        volume = max(0.0, float(trade.get('volume_index', 0.0)))
        friction = _clamp(float(trade.get('friction', 0.0)))
        distance = max(0.0, float(trade.get('distance_km', route.get('distance_km', 0.0))))
        source_prosperity = _estimate(source_economy, 'prosperity_index', clamp=True)
        target_trade_dependency = _estimate(target_economy, 'trade_dependency_index', clamp=True)
        source_resource_output = _estimate(source_economy, 'resource_output_index')
        target_population = _estimate(target_economy, 'population')
        supply_index = _conditional(lambda source_resource_output, source_prosperity: _clamp(source_resource_output / 260.0 * 0.3 + source_prosperity * 0.32 + volume / 140.0 * 0.2 + (1.0 - friction) * 0.18), source_resource_output, source_prosperity)
        target_urban_services = _estimate(target_economy, 'urban_services_index')
        demand_index = _conditional(lambda target_population, target_trade_dependency, target_urban_services: _clamp(target_population / 1000000000.0 * 0.28 + target_trade_dependency * 0.34 + volume / 140.0 * 0.18 + target_urban_services / 260.0 * 0.2), target_population, target_trade_dependency, target_urban_services)
        regional_pressure = _conditional(lambda a, b: max(a, b), conflict_pressure[source_region], conflict_pressure[target_region])
        disruption_risk = _conditional(lambda regional_pressure: _clamp(friction * 0.36 + regional_pressure * 0.44 + distance / 9000.0 * 0.2), regional_pressure)
        price_spread = _conditional(lambda demand_index, supply_index: _clamp(friction * 0.48 + abs(demand_index - supply_index) * 0.28 + distance / 9000.0 * 0.24), demand_index, supply_index)
        source_network = network_by_region.get(source_region, {})
        target_network = network_by_region.get(target_region, {})
        network_access = (float(source_network.get('transport_efficiency_index', 0.0)) + float(target_network.get('transport_efficiency_index', 0.0))) * 0.5
        market_access = _conditional(lambda disruption_risk: _clamp((1.0 - friction) * 0.32 + volume / 140.0 * 0.24 + network_access * 0.28 + (1.0 - disruption_risk) * 0.16), disruption_risk)
        food_security_link = _conditional(lambda a, b: _clamp((a + b) * 0.5), _estimate(source_economy, 'food_security_index'), _estimate(target_economy, 'food_security_index'))
        tax_revenue = _conditional(lambda disruption_risk: max(0.0, volume * (0.035 + (0.018 if bool(trade.get('interregional', False)) else 0.0)) * (1.0 - disruption_risk * 0.2)), disruption_risk)
        exchanges.append({'id': len(exchanges), 'trade_flow_id': trade_id, 'route_id': route_id, 'from_settlement_id': int(trade.get('from', route.get('from', -1))), 'to_settlement_id': int(trade.get('to', route.get('to', -1))), 'region_from': source_region, 'region_to': target_region, 'primary_good': str(trade.get('primary_good', 'mixed_goods')), 'interregional': bool(trade.get('interregional', False)), 'distance_km': round(distance, 6), 'volume_index': round(volume, 6), 'friction': round(friction, 6), 'supply_index': _conditional(lambda supply_index: round(supply_index, 6), supply_index), 'demand_index': _conditional(lambda demand_index: round(demand_index, 6), demand_index), 'price_spread_index': _conditional(lambda price_spread: round(price_spread, 6), price_spread), 'market_access_index': _conditional(lambda market_access: round(market_access, 6), market_access), 'tax_revenue_index': _conditional(lambda tax_revenue: round(tax_revenue, 6), tax_revenue), 'food_security_link_index': _conditional(lambda food_security_link: round(food_security_link, 6), food_security_link), 'disruption_risk_index': _conditional(lambda disruption_risk: round(disruption_risk, 6), disruption_risk)})
        market_access_sum = _conditional(lambda a, b: a + b, market_access_sum, market_access)
        disruption_sum = _conditional(lambda a, b: a + b, disruption_sum, disruption_risk)
        total_market_volume += volume
        interregional_market_count += int(bool(trade.get('interregional', False)))
    network_count = len(networks)
    market_count = len(exchanges)
    summary = {'logistics_network_count': network_count, 'logistics_route_link_count': total_route_links, 'market_exchange_count': market_count, 'interregional_market_exchange_count': interregional_market_count, 'total_market_exchange_volume_index': round(total_market_volume, 6), 'mean_logistics_transport_efficiency_index': round(efficiency_sum / network_count, 6) if network_count else 0.0, 'mean_logistics_resilience_index': _conditional(lambda resilience_sum: round(resilience_sum / network_count, 6), resilience_sum) if network_count else 0.0, 'mean_market_access_index': _conditional(lambda market_access_sum: round(market_access_sum / market_count, 6), market_access_sum) if market_count else 0.0, 'mean_market_disruption_risk_index': _conditional(lambda disruption_sum: round(disruption_sum / market_count, 6), disruption_sum) if market_count else 0.0}
    # V2 explicitly aggregates its serialized estimates. Independently rebuild
    # those values instead of using the historical unrounded accumulators.
    for key, rows, field, mean in (
        ('total_market_exchange_volume_index', exchanges, 'volume_index', False),
        ('mean_logistics_transport_efficiency_index', networks, 'transport_efficiency_index', True),
        ('mean_logistics_resilience_index', networks, 'logistics_resilience_index', True),
        ('mean_market_access_index', exchanges, 'market_access_index', True),
        ('mean_market_disruption_risk_index', exchanges, 'disruption_risk_index', True),
    ):
        values = [row[field] for row in rows]
        summary[key] = (None if any(value is None for value in values)
                        else round(sum(values) / max(1, len(values)) if mean else sum(values), 6))
    return (networks, exchanges, summary)
