"""Independent nullable replay adapted from the retained historical oracle.

The numerical producer is not imported. Static arithmetic adaptation provenance
is retained alongside the stage review; source completeness gates precede replay.
"""
from __future__ import annotations
import math
from typing import Any
from .demographic_agents_validation import (_by_region, _population_history_by_population_region,
    _final_step, _settlements_by_region, _sorted_eras, _person_name, _cohort_specs,
    ROLE_SEQUENCE, _demographic_agent_model, _individual_life_event_model)


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


def _available_cohort_specs(urban,migration,pressure):
    if any(v is None for v in (urban,migration,pressure)):
        return [("rural_household",None,5.1),("urban_household",None,3.8),("mobile_household",None,4.2)]
    return _cohort_specs(urban,migration,pressure)


def _available_dominant_sector(payload,region,firms):
    economy=next(e for e in payload["economy_histories"] if e["region_id"]==region)["steps"][-1]
    fields=("agricultural_output_index","resource_output_index","trade_output_index","urban_services_index","administration_cost_index")
    selected=[f for f in firms if f["region_id"]==region]
    if any(economy[k] is None for k in fields) or any(f["employment_capacity"] is None for f in selected):return None
    return max(selected,key=lambda f:f["employment_capacity"])["sector"] if selected else "subsistence"

def _market_pressure_by_region(payload: dict[str, Any]) -> dict[int, float]:
    pressure: dict[int, float] = {}
    for market in payload.get('market_exchanges', []):
        disruption = _nullable_clamp(_nullable_float(market.get('disruption_risk_index', 0.0)))
        dependency = _nullable_clamp(_nullable_float(market.get('market_access_index', 0.0)))
        value = _nullable_clamp(_nullable_add(_nullable_add(_nullable_mul(disruption, 0.62), _nullable_mul(dependency, 0.18)), _nullable_mul(_nullable_float(market.get('friction', 0.0)), 0.2)))
        for key in ('region_from', 'region_to'):
            region_id = int(market.get(key, _nullable_neg(1)))
            if region_id >= 0:
                pressure[region_id] = _nullable_max(pressure.get(region_id, 0.0), value)
    return pressure

def _replay_aggregate_numeric(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]], dict[str, Any]]:
    population_regions = payload['population_regions']
    population_histories = _population_history_by_population_region(payload)
    economy_by_region = _by_region(payload['economy_histories'])
    logistics_by_region = _by_region(payload['logistics_networks'])
    market_pressure_by_region = _market_pressure_by_region(payload)
    settlements_by_region = _settlements_by_region(payload)
    regions_by_id = {int(region.get('id', _nullable_neg(1))): region for region in payload['political_regions']}
    households: list[dict[str, Any]] = []
    firms: list[dict[str, Any]] = []
    histories: list[dict[str, Any]] = []
    population_annotations: dict[int, dict[str, Any]] = {}
    political_annotations: dict[int, dict[str, Any]] = {}
    household_population_total = 0.0
    household_resilience_sum = 0.0
    household_migration_sum = 0.0
    household_consumption_sum = 0.0
    high_vulnerability_households = 0
    for population_region in sorted(population_regions, key=lambda item: int(item.get('id', _nullable_neg(1)))):
        population_region_id = int(population_region.get('id', _nullable_neg(1)))
        region_id = int(population_region.get('region_id', _nullable_neg(1)))
        history = population_histories.get(population_region_id, {})
        final_step = _final_step(economy_by_region.get(region_id, {}))
        logistics = logistics_by_region.get(region_id, {})
        final_population = _nullable_max(0.0, _nullable_float(history.get('final_population', population_region.get('estimated_population', 0.0))))
        urbanization = _nullable_clamp(_nullable_float(population_region.get('urbanization_fraction', 0.0)))
        migration_balance = _nullable_float(population_region.get('migration_balance', 0.0))
        pressure = _nullable_clamp(_nullable_float(population_region.get('population_pressure', 0.0)))
        hazard = _nullable_clamp(_nullable_float(population_region.get('hazard_mortality_index', 0.0)))
        water_security = _nullable_clamp(_nullable_float(population_region.get('water_security_index', 0.0)))
        food_security = _nullable_clamp(_nullable_float(final_step.get('food_security_index', 0.0)))
        prosperity = _nullable_clamp(_nullable_float(final_step.get('prosperity_index', 0.0)))
        trade_dependency = _nullable_clamp(_nullable_float(final_step.get('trade_dependency_index', 0.0)))
        logistics_resilience = _nullable_clamp(_nullable_float(logistics.get('logistics_resilience_index', 0.0)))
        market_pressure = market_pressure_by_region.get(region_id, 0.0)
        cohort_ids: list[int] = []
        allocated_population = 0.0
        specs = _available_cohort_specs(urbanization, migration_balance, pressure)
        for index, (cohort_type, fraction, household_size) in enumerate(specs):
            if final_population == 0.0:
                population = 0.0
            elif index == _nullable_sub(len(specs), 1):
                population = _nullable_max(0.0, _nullable_sub(final_population, allocated_population))
            else:
                population = _nullable_max(0.0, _nullable_mul(final_population, fraction))
                allocated_population = _nullable_add(allocated_population, population)
            cohort_modifier = {'rural_household': 0.04, 'urban_household': _nullable_neg(0.02), 'mobile_household': 0.1}[cohort_type]
            vulnerability = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(hazard, 0.3), _nullable_mul(pressure, 0.24)), _nullable_mul(_nullable_sub(1.0, water_security), 0.2)), _nullable_mul(_nullable_sub(1.0, food_security), 0.14)), _nullable_mul(market_pressure, 0.08)), cohort_modifier))
            migration_propensity = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(_nullable_abs(migration_balance), 0.38), _nullable_mul(pressure, 0.18)), _nullable_mul(vulnerability, 0.22)), _nullable_mul(_nullable_sub(1.0, logistics_resilience), 0.14)), 0.12 if cohort_type == 'mobile_household' else 0.0))
            consumption_pressure = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(pressure, 0.34), _nullable_mul(_nullable_sub(1.0, food_security), 0.24)), _nullable_mul(_nullable_sub(1.0, prosperity), 0.18)), _nullable_mul(trade_dependency, 0.14)), _nullable_mul(vulnerability, 0.1)))
            income = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(prosperity, 0.42), _nullable_mul(_nullable_sub(1.0, vulnerability), 0.22)), _nullable_mul(urbanization, 0.16)), _nullable_mul(logistics_resilience, 0.2)))
            labor_participation = _nullable_clamp(_nullable_add(_nullable_sub(_nullable_add(0.43, _nullable_mul(prosperity, 0.18)), _nullable_mul(vulnerability, 0.12)), 0.07 if cohort_type == 'urban_household' else 0.0))
            fertility_rate = _nullable_max(0.0, _nullable_sub(_nullable_add(_nullable_add(0.0007, _nullable_mul(_nullable_sub(1.0, urbanization), 0.0007)), _nullable_mul(pressure, 0.0004)), _nullable_mul(vulnerability, 0.00025)))
            mortality_risk = _nullable_clamp(_nullable_add(_nullable_add(_nullable_mul(hazard, 0.44), _nullable_mul(vulnerability, 0.38)), _nullable_mul(pressure, 0.18)))
            cohort_id = len(households)
            households.append({'id': cohort_id, 'population_region_id': population_region_id, 'region_id': region_id, 'culture_region_id': int(population_region.get('culture_region_id', _nullable_neg(1))), 'language_region_id': int(population_region.get('language_region_id', _nullable_neg(1))), 'cohort_type': cohort_type, 'population': _nullable_round(population, 6), 'household_count': _nullable_round(_nullable_div(population, _nullable_max(1.0, household_size)), 6), 'average_household_size': _nullable_round(household_size, 6), 'urbanization_fraction': _nullable_round(urbanization, 6), 'water_security_index': _nullable_round(water_security, 6), 'food_security_index': _nullable_round(food_security, 6), 'income_index': _nullable_round(income, 6), 'consumption_pressure_index': _nullable_round(consumption_pressure, 6), 'vulnerability_index': _nullable_round(vulnerability, 6), 'migration_propensity_index': _nullable_round(migration_propensity, 6), 'fertility_rate_per_year': _nullable_round(fertility_rate, 8), 'mortality_risk_index': _nullable_round(mortality_risk, 6), 'labor_participation_index': _nullable_round(labor_participation, 6)})
            cohort_ids.append(cohort_id)
            household_population_total = _nullable_add(household_population_total, population)
            household_resilience_sum = _nullable_add(household_resilience_sum, _nullable_sub(1.0, vulnerability))
            household_migration_sum = _nullable_add(household_migration_sum, migration_propensity)
            household_consumption_sum = _nullable_add(household_consumption_sum, consumption_pressure)
            high_vulnerability_households = _nullable_add(high_vulnerability_households, None if vulnerability is None else int(vulnerability >= 0.65))
        population_annotations[population_region_id] = {'household_cohort_ids': cohort_ids, 'household_cohort_count': len(cohort_ids), 'representative_household_population': _nullable_round(_nullable_sum((_nullable_float(households[cohort_id]['population']) for cohort_id in cohort_ids)), 6)}
    firm_productivity_sum = 0.0
    firm_market_dependency_sum = 0.0
    firm_supply_chain_risk_sum = 0.0
    firm_employment_total = 0.0
    for economy in sorted(payload['economy_histories'], key=lambda item: int(item.get('region_id', _nullable_neg(1)))):
        region_id = int(economy.get('region_id', _nullable_neg(1)))
        if region_id < 0:
            continue
        final_step = _final_step(economy)
        population = _nullable_max(0.0, _nullable_float(final_step.get('population', 0.0)))
        gross_output = _nullable_max(1.0, _nullable_float(final_step.get('gross_output_index', economy.get('final_gross_output_index', 1.0))))
        prosperity = _nullable_clamp(_nullable_float(final_step.get('prosperity_index', 0.0)))
        trade_dependency = _nullable_clamp(_nullable_float(final_step.get('trade_dependency_index', 0.0)))
        stability = _nullable_clamp(_nullable_float(final_step.get('stability_index', 0.0)))
        military_burden = _nullable_clamp(_nullable_float(final_step.get('military_burden_index', 0.0)))
        logistics = logistics_by_region.get(region_id, {})
        logistics_resilience = _nullable_clamp(_nullable_float(logistics.get('logistics_resilience_index', 0.0)))
        chokepoint = _nullable_clamp(_nullable_float(logistics.get('chokepoint_exposure_index', 0.0)))
        settlement_ids = settlements_by_region.get(region_id, [])
        capital_settlement_id = int(regions_by_id.get(region_id, {}).get('capital_settlement_id', _nullable_neg(1)))
        sector_outputs = [('agriculture', _nullable_float(final_step.get('agricultural_output_index', 0.0)), 0.3), ('resource', _nullable_float(final_step.get('resource_output_index', 0.0)), 0.44), ('trade', _nullable_float(final_step.get('trade_output_index', 0.0)), 0.82), ('urban_services', _nullable_float(final_step.get('urban_services_index', 0.0)), 0.56), ('administration', _nullable_float(final_step.get('administration_cost_index', 0.0)), 0.24)]
        firm_ids: list[int] = []
        for index, (sector, output, base_dependency) in enumerate(sector_outputs):
            if output is None or output <= 0.0:
                continue
            output_share = _nullable_clamp(_nullable_div(output, gross_output))
            market_dependency = _nullable_clamp(_nullable_add(_nullable_add(_nullable_mul(base_dependency, 0.52), _nullable_mul(trade_dependency, 0.34)), _nullable_mul(output_share, 0.14)))
            productivity = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(output_share, 0.42), _nullable_mul(prosperity, 0.3)), _nullable_mul(stability, 0.18)), _nullable_mul(logistics_resilience, 0.1)))
            supply_chain_risk = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(chokepoint, 0.32), _nullable_mul(market_dependency, 0.26)), _nullable_mul(_nullable_sub(1.0, logistics_resilience), 0.24)), _nullable_mul(military_burden, 0.18)))
            employment = _nullable_mul(_nullable_mul(population, output_share), _nullable_add(0.3, _nullable_mul(productivity, 0.28)))
            tax_contribution = _nullable_mul(_nullable_mul(output, _nullable_add(0.07, _nullable_mul(market_dependency, 0.025))), _nullable_sub(1.0, _nullable_mul(supply_chain_risk, 0.16)))
            settlement_id = capital_settlement_id if index == 0 or not settlement_ids else settlement_ids[_nullable_mod(index, len(settlement_ids))]
            firm_id = len(firms)
            firms.append({'id': firm_id, 'region_id': region_id, 'population_region_id': int(economy.get('population_region_id', _nullable_neg(1))), 'settlement_id': settlement_id, 'sector': sector, 'output_index': _nullable_round(_nullable_max(0.0, output), 6), 'employment_capacity': _nullable_round(employment, 6), 'wage_index': _nullable_round(_nullable_clamp(_nullable_add(_nullable_add(_nullable_mul(prosperity, 0.45), _nullable_mul(productivity, 0.35)), _nullable_mul(_nullable_sub(1.0, supply_chain_risk), 0.2))), 6), 'productivity_index': _nullable_round(productivity, 6), 'market_dependency_index': _nullable_round(market_dependency, 6), 'capital_stock_index': _nullable_round(_nullable_clamp(_nullable_add(_nullable_add(_nullable_mul(_nullable_div(output, 260.0), 0.48), _nullable_mul(prosperity, 0.26)), _nullable_mul(logistics_resilience, 0.26))), 6), 'supply_chain_risk_index': _nullable_round(supply_chain_risk, 6), 'tax_contribution_index': _nullable_round(tax_contribution, 6)})
            firm_ids.append(firm_id)
            firm_productivity_sum = _nullable_add(firm_productivity_sum, productivity)
            firm_market_dependency_sum = _nullable_add(firm_market_dependency_sum, market_dependency)
            firm_supply_chain_risk_sum = _nullable_add(firm_supply_chain_risk_sum, supply_chain_risk)
            firm_employment_total = _nullable_add(firm_employment_total, employment)
        if region_id in regions_by_id:
            political_annotations[region_id] = {'firm_agent_ids': firm_ids, 'firm_agent_count': len(firm_ids)}
    demographic_vulnerability_sum = 0.0
    demographic_step_count = 0
    for population_region in sorted(population_regions, key=lambda item: int(item.get('id', _nullable_neg(1)))):
        population_region_id = int(population_region.get('id', _nullable_neg(1)))
        region_id = int(population_region.get('region_id', _nullable_neg(1)))
        history = population_histories.get(population_region_id, {})
        cohort_ids = population_annotations[population_region_id]['household_cohort_ids']
        cohort_population = _nullable_max(1.0, _nullable_sum((_nullable_float(households[cohort_id]['population']) for cohort_id in cohort_ids)))
        labor_average = _nullable_div(_nullable_sum((_nullable_mul(_nullable_float(households[cohort_id]['labor_participation_index']), _nullable_float(households[cohort_id]['population'])) for cohort_id in cohort_ids)), cohort_population) if cohort_ids else 0.45
        steps: list[dict[str, Any]] = []
        for index, step in enumerate(history.get('steps', [])):
            start_population = _nullable_max(0.0, _nullable_float(step.get('start_population', 0.0)))
            end_population = _nullable_max(0.0, _nullable_float(step.get('end_population', 0.0)))
            pressure = _nullable_clamp(_nullable_float(step.get('pressure_index', 0.0)))
            hazard = _nullable_clamp(_nullable_float(step.get('hazard_mortality_index', population_region.get('hazard_mortality_index', 0.0))))
            conflict_loss = _nullable_max(0.0, _nullable_float(step.get('conflict_loss', 0.0)))
            migration_delta = _nullable_float(step.get('migration_delta', 0.0))
            loss_fraction = _nullable_clamp(_nullable_div(conflict_loss, _nullable_max(1.0, start_population)))
            migration_propensity = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(_nullable_div(_nullable_abs(migration_delta), _nullable_max(1.0, start_population)), 8.0), _nullable_mul(pressure, 0.2)), _nullable_mul(hazard, 0.18)), _nullable_mul(loss_fraction, 0.28)))
            vulnerability = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(hazard, 0.32), _nullable_mul(pressure, 0.26)), _nullable_mul(loss_fraction, 0.28)), _nullable_mul(migration_propensity, 0.14)))
            working_population = _nullable_mul(end_population, labor_average)
            dependent_population = _nullable_max(0.0, _nullable_sub(end_population, working_population))
            consumption_pressure = _nullable_clamp(_nullable_add(_nullable_add(_nullable_add(_nullable_mul(pressure, 0.42), _nullable_mul(_nullable_div(dependent_population, _nullable_max(1.0, end_population)), 0.24)), _nullable_mul(vulnerability, 0.22)), _nullable_mul(loss_fraction, 0.12)))
            steps.append({'era_id': int(step.get('era_id', _nullable_neg(1))), 'stage_index': _nullable_add(index, 1), 'start_year_bp': _nullable_round(_nullable_float(step.get('start_year_bp', 0.0)), 6), 'end_year_bp': _nullable_round(_nullable_float(step.get('end_year_bp', 0.0)), 6), 'start_population': _nullable_round(start_population, 6), 'end_population': _nullable_round(end_population, 6), 'working_population': _nullable_round(working_population, 6), 'dependent_population': _nullable_round(dependent_population, 6), 'migration_propensity_index': _nullable_round(migration_propensity, 6), 'consumption_pressure_index': _nullable_round(consumption_pressure, 6), 'vulnerability_index': _nullable_round(vulnerability, 6), 'labor_participation_index': _nullable_round(labor_average, 6)})
            demographic_vulnerability_sum = _nullable_add(demographic_vulnerability_sum, vulnerability)
            demographic_step_count = _nullable_add(demographic_step_count, 1)
        history_id = len(histories)
        histories.append({'id': history_id, 'population_region_id': population_region_id, 'region_id': region_id, 'household_cohort_ids': list(cohort_ids), 'firm_agent_ids': list(political_annotations.get(region_id, {}).get('firm_agent_ids', [])), 'step_count': len(steps), 'final_agent_population': _nullable_round(_nullable_float(history.get('final_population', 0.0)), 6), 'mean_labor_participation_index': _nullable_round(labor_average, 6), 'steps': steps})
        population_annotations[population_region_id]['demographic_agent_history_id'] = history_id
    household_count = len(households)
    firm_count = len(firms)
    summary = {'household_cohort_count': household_count, 'firm_agent_count': firm_count, 'demographic_agent_history_count': len(histories), 'demographic_agent_step_count': demographic_step_count, 'total_household_cohort_population': _nullable_round(household_population_total, 6), 'total_firm_employment_capacity': _nullable_round(firm_employment_total, 6), 'mean_household_resilience_index': _nullable_round(_nullable_div(household_resilience_sum, household_count), 6) if household_count else 0.0, 'mean_household_migration_propensity_index': _nullable_round(_nullable_div(household_migration_sum, household_count), 6) if household_count else 0.0, 'mean_household_consumption_pressure_index': _nullable_round(_nullable_div(household_consumption_sum, household_count), 6) if household_count else 0.0, 'mean_firm_productivity_index': _nullable_round(_nullable_div(firm_productivity_sum, firm_count), 6) if firm_count else 0.0, 'mean_firm_market_dependency_index': _nullable_round(_nullable_div(firm_market_dependency_sum, firm_count), 6) if firm_count else 0.0, 'mean_firm_supply_chain_risk_index': _nullable_round(_nullable_div(firm_supply_chain_risk_sum, firm_count), 6) if firm_count else 0.0, 'mean_demographic_vulnerability_index': _nullable_round(_nullable_div(demographic_vulnerability_sum, demographic_step_count), 6) if demographic_step_count else 0.0, 'high_vulnerability_household_count': high_vulnerability_households}
    return (households, firms, histories, population_annotations, political_annotations, summary)

def _replay_individual_numeric(payload: dict[str, Any], households: list[dict[str, Any]], firms: list[dict[str, Any]], population_annotations: dict[int, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    eras = _sorted_eras(payload)
    history_sources = _population_history_by_population_region(payload)
    individuals: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    birth_event_count = 0
    death_event_count = 0
    marriage_event_count = 0
    property_transfer_event_count = 0
    individual_lifespan_sum = 0.0
    property_transfer_value_sum = 0.0
    for population_region in sorted(payload['population_regions'], key=lambda item: int(item.get('id', _nullable_neg(1)))):
        population_region_id = int(population_region.get('id', _nullable_neg(1)))
        region_id = int(population_region.get('region_id', _nullable_neg(1)))
        culture_id = int(population_region.get('culture_region_id', _nullable_neg(1)))
        language_id = int(population_region.get('language_region_id', _nullable_neg(1)))
        represented = history_sources[population_region_id]['final_population']
        population_annotations[population_region_id]['individual_sampling_available'] = represented is not None
        population_annotations[population_region_id]['individual_sampling_status'] = 'unavailable_population' if represented is None else 'known_zero_population' if represented == 0.0 else 'sampled_positive_population'
        population_annotations[population_region_id]['individual_agent_ids'] = []
        population_annotations[population_region_id]['individual_agent_count'] = 0
        if represented is None or represented == 0.0:
            continue
        cohort_ids = list(population_annotations[population_region_id].get('household_cohort_ids', []))
        if not cohort_ids:
            continue
        dominant_sector = _available_dominant_sector(payload, region_id, firms)
        region_person_ids: list[int] = []
        sample_count = _nullable_min(6, _nullable_max(2, _nullable_mul(len(cohort_ids), 2)))
        for index in range(sample_count):
            cohort_id = cohort_ids[_nullable_mod(index, len(cohort_ids))]
            cohort = households[cohort_id]
            cohort_population = _nullable_max(1.0, _nullable_float(cohort.get('population', 0.0)))
            household_count = _nullable_max(1.0, _nullable_float(cohort.get('household_count', 0.0)))
            fertility = _nullable_max(0.0, _nullable_float(cohort.get('fertility_rate_per_year', 0.0)))
            mortality = _nullable_clamp(_nullable_float(cohort.get('mortality_risk_index', 0.0)))
            vulnerability = _nullable_clamp(_nullable_float(cohort.get('vulnerability_index', 0.0)))
            migration = _nullable_clamp(_nullable_float(cohort.get('migration_propensity_index', 0.0)))
            income = _nullable_clamp(_nullable_float(cohort.get('income_index', 0.0)))
            birth_era = eras[_nullable_mod(index, len(eras))]
            death_era = eras[_nullable_neg(1)]
            life_expectancy = _nullable_max(18.0, _nullable_add(_nullable_sub(_nullable_sub(78.0, _nullable_mul(mortality, 26.0)), _nullable_mul(vulnerability, 18.0)), _nullable_mul(income, 10.0)))
            birth_year_bp = _nullable_max(_nullable_float(death_era.get('end_year_bp', 0.0)), _nullable_sub(_nullable_sub(_nullable_float(birth_era.get('start_year_bp', 0.0)), 16.0), _nullable_mul(index, 7.0)))
            death_year_bp = _nullable_max(_nullable_float(death_era.get('end_year_bp', 0.0)), _nullable_sub(birth_year_bp, life_expectancy))
            household_share = _nullable_div(cohort_population, household_count)
            property_value = _nullable_max(0.0, _nullable_mul(_nullable_mul(household_share, _nullable_add(0.24, _nullable_mul(income, 0.46))), _nullable_sub(1.0, _nullable_mul(vulnerability, 0.22))))
            person_id = len(individuals)
            role = ROLE_SEQUENCE[_nullable_mod(_nullable_add(region_id, index), len(ROLE_SEQUENCE))]
            if role == 'farmer' and dominant_sector != 'agriculture' and (_nullable_mod(index, 3) == 0):
                role = dominant_sector
            individuals.append({'id': person_id, 'population_region_id': population_region_id, 'region_id': region_id, 'household_cohort_id': cohort_id, 'culture_region_id': culture_id, 'language_region_id': language_id, 'name': _person_name(region_id, index, culture_id), 'role': role, 'birth_year_bp': _nullable_round(birth_year_bp, 6), 'death_year_bp': _nullable_round(death_year_bp, 6), 'lifespan_years': _nullable_round(_nullable_max(0.0, _nullable_sub(birth_year_bp, death_year_bp)), 6), 'married_person_id': _nullable_neg(1), 'parent_person_ids': [], 'child_person_ids': [], 'property_value_index': _nullable_round(property_value, 6), 'mobility_index': _nullable_round(migration, 6), 'vulnerability_index': _nullable_round(vulnerability, 6), 'event_ids': [], 'event_count': 0})
            region_person_ids.append(person_id)
            individual_lifespan_sum = _nullable_add(individual_lifespan_sum, _nullable_max(0.0, _nullable_sub(birth_year_bp, death_year_bp)))
            birth_event_id = len(events)
            events.append({'id': birth_event_id, 'person_id': person_id, 'related_person_id': _nullable_neg(1), 'population_region_id': population_region_id, 'region_id': region_id, 'household_cohort_id': cohort_id, 'era_id': int(birth_era.get('id', _nullable_neg(1))), 'event_type': 'birth', 'year_bp': _nullable_round(birth_year_bp, 6), 'property_value_index': 0.0, 'demographic_pressure_index': _nullable_round(_nullable_clamp(_nullable_add(_nullable_mul(fertility, 320.0), _nullable_mul(migration, 0.18))), 6), 'mortality_risk_index': _nullable_round(mortality, 6), 'inheritance_fraction': 0.0})
            individuals[person_id]['event_ids'].append(birth_event_id)
            birth_event_count = _nullable_add(birth_event_count, 1)
            if index >= 2:
                parent_ids = [region_person_ids[_nullable_sub(index, 2)]]
                if index >= 3:
                    parent_ids.append(region_person_ids[_nullable_sub(index, 3)])
                individuals[person_id]['parent_person_ids'] = parent_ids
                for parent_id in parent_ids:
                    individuals[parent_id]['child_person_ids'].append(person_id)
            if _nullable_mod(index, 2) == 1:
                spouse_id = region_person_ids[_nullable_sub(index, 1)]
                marriage_year = _nullable_max(death_year_bp, _nullable_sub(_nullable_sub(birth_year_bp, 22.0), _nullable_mul(vulnerability, 6.0)))
                individuals[person_id]['married_person_id'] = spouse_id
                individuals[spouse_id]['married_person_id'] = person_id
                for participant_id, related_id in ((person_id, spouse_id), (spouse_id, person_id)):
                    marriage_event_id = len(events)
                    events.append({'id': marriage_event_id, 'person_id': participant_id, 'related_person_id': related_id, 'population_region_id': population_region_id, 'region_id': region_id, 'household_cohort_id': int(individuals[participant_id]['household_cohort_id']), 'era_id': int(birth_era.get('id', _nullable_neg(1))), 'event_type': 'marriage', 'year_bp': _nullable_round(marriage_year, 6), 'property_value_index': 0.0, 'demographic_pressure_index': _nullable_round(_nullable_clamp(_nullable_add(_nullable_mul(migration, 0.26), _nullable_mul(vulnerability, 0.2))), 6), 'mortality_risk_index': _nullable_round(mortality, 6), 'inheritance_fraction': 0.0})
                    individuals[participant_id]['event_ids'].append(marriage_event_id)
                    marriage_event_count = _nullable_add(marriage_event_count, 1)
            transfer_year = _nullable_max(death_year_bp, _nullable_sub(birth_year_bp, _nullable_max(1.0, _nullable_mul(life_expectancy, 0.72))))
            recipient_id = region_person_ids[_nullable_sub(index, 2)] if index >= 2 else _nullable_neg(1)
            transfer_fraction = 0.48 if recipient_id >= 0 else 0.2
            transfer_value = _nullable_mul(property_value, transfer_fraction)
            property_transfer_id = len(events)
            events.append({'id': property_transfer_id, 'person_id': person_id, 'related_person_id': recipient_id, 'population_region_id': population_region_id, 'region_id': region_id, 'household_cohort_id': cohort_id, 'era_id': int(death_era.get('id', _nullable_neg(1))), 'event_type': 'property_transfer', 'year_bp': _nullable_round(transfer_year, 6), 'property_value_index': _nullable_round(transfer_value, 6), 'demographic_pressure_index': _nullable_round(_nullable_clamp(_nullable_add(_nullable_mul(migration, 0.22), _nullable_mul(vulnerability, 0.24))), 6), 'mortality_risk_index': _nullable_round(mortality, 6), 'inheritance_fraction': _nullable_round(transfer_fraction, 6)})
            individuals[person_id]['event_ids'].append(property_transfer_id)
            property_transfer_event_count = _nullable_add(property_transfer_event_count, 1)
            property_transfer_value_sum = _nullable_add(property_transfer_value_sum, transfer_value)
            death_event_id = len(events)
            events.append({'id': death_event_id, 'person_id': person_id, 'related_person_id': _nullable_neg(1), 'population_region_id': population_region_id, 'region_id': region_id, 'household_cohort_id': cohort_id, 'era_id': int(death_era.get('id', _nullable_neg(1))), 'event_type': 'death', 'year_bp': _nullable_round(death_year_bp, 6), 'property_value_index': 0.0, 'demographic_pressure_index': _nullable_round(_nullable_clamp(_nullable_add(_nullable_mul(vulnerability, 0.42), _nullable_mul(mortality, 0.38))), 6), 'mortality_risk_index': _nullable_round(mortality, 6), 'inheritance_fraction': 0.0})
            individuals[person_id]['event_ids'].append(death_event_id)
            death_event_count = _nullable_add(death_event_count, 1)
        for person_id in region_person_ids:
            individuals[person_id]['event_count'] = len(individuals[person_id]['event_ids'])
        population_annotations[population_region_id]['individual_agent_ids'] = region_person_ids
        population_annotations[population_region_id]['individual_agent_count'] = len(region_person_ids)
    individual_count = len(individuals)
    summary = {'individual_agent_count': individual_count, 'individual_life_event_count': len(events), 'individual_birth_event_count': birth_event_count, 'individual_death_event_count': death_event_count, 'individual_marriage_event_count': marriage_event_count, 'property_transfer_event_count': property_transfer_event_count, 'total_property_transfer_value_index': _nullable_round(property_transfer_value_sum, 6), 'mean_individual_lifespan_years': _nullable_round(_nullable_div(individual_lifespan_sum, individual_count), 6) if individual_count else 0.0}
    return (individuals, events, summary)

HOUSEHOLD_ESTIMATES=("population","household_count","average_household_size","urbanization_fraction","water_security_index","food_security_index","income_index","consumption_pressure_index","vulnerability_index","migration_propensity_index","fertility_rate_per_year","mortality_risk_index","labor_participation_index")
FIRM_ESTIMATES=("output_index","employment_capacity","wage_index","productivity_index","market_dependency_index","capital_stock_index","supply_chain_risk_index","tax_contribution_index")
HISTORY_ESTIMATES=("final_agent_population","mean_labor_participation_index")
STEP_ESTIMATES=("start_population","end_population","working_population","dependent_population","migration_propensity_index","consumption_pressure_index","vulnerability_index","labor_participation_index")
PERSON_ESTIMATES=("birth_year_bp","death_year_bp","lifespan_years","property_value_index","mobility_index","vulnerability_index")
EVENT_ESTIMATES=("year_bp","property_value_index","demographic_pressure_index","mortality_risk_index","inheritance_fraction")
AGGREGATE_ESTIMATES=("total_household_cohort_population","total_firm_employment_capacity","mean_household_resilience_index","mean_household_migration_propensity_index","mean_household_consumption_pressure_index","mean_firm_productivity_index","mean_firm_market_dependency_index","mean_firm_supply_chain_risk_index","mean_demographic_vulnerability_index","high_vulnerability_household_count")
LIFE_ESTIMATES=("total_property_transfer_value_index","mean_individual_lifespan_years")
COLLECTIONS=("household_cohorts","firm_agents","demographic_agent_histories","individual_agents","individual_life_events")
POPULATION_ANNOTATIONS=("household_cohort_ids","household_cohort_count","representative_household_population","demographic_agent_history_id","individual_agent_ids","individual_agent_count","demographic_estimate_availability","individual_sampling_available","individual_sampling_status")
POLITICAL_ANNOTATIONS=("firm_agent_ids","firm_agent_count","firm_candidate_sector_coverage","firm_selection_complete")
SUMMARY_FIELDS=(*AGGREGATE_ESTIMATES,*LIFE_ESTIMATES,"household_cohort_count","firm_agent_count","demographic_agent_history_count","demographic_agent_step_count","individual_agent_count","individual_life_event_count","individual_birth_event_count","individual_death_event_count","individual_marriage_event_count","property_transfer_event_count","demographic_agent_model","individual_life_event_model","demographic_summary_estimate_availability","individual_summary_estimate_availability","firm_selection_complete","firm_candidate_sector_count","firm_unavailable_sector_count","individual_sampling_complete","individual_sampling_unavailable_region_ids","individual_sampling_known_zero_region_ids")


def demographic_model_v2():
    return {**_demographic_agent_model(),"model_type":"causal_population_economy_logistics_household_firm_demographic_history_v2",
        "source_population_region_model":"causal_area_weighted_capacity_occupancy_population_regions_v2",
        "source_population_history_model":"causal_era_snapshot_logistic_migration_conflict_population_history_v2",
        "source_economy_history_model":"causal_population_trade_conflict_treasury_economy_history_v2",
        "source_logistics_exchange_model":"causal_region_route_trade_economy_logistics_exchange_v2",
        "household_model":"three_template_nullable_normalized_population_cohorts_v2",
        "firm_selection_policy":"known_positive_firms_with_explicit_unknown_candidate_sector_coverage",
        "availability_policy":"typed_per_field_null_unknown_no_parent_default_substitution",
        "aggregate_policy":"complete_candidate_scope_and_complete_estimates_or_null_no_partial_renormalization"}


def life_model_v2():
    return {**_individual_life_event_model(),"model_type":"causal_household_firm_era_sampled_individual_life_event_graph_v2",
        "source_demographic_agent_model":"causal_population_economy_logistics_household_firm_demographic_history_v2",
        "source_historical_event_model":"causal_region_culture_language_trade_site_timeline_v2",
        "sampling_model":"six_positive_population_template_people_zero_complete_empty_unknown_unavailable_v2",
        "availability_policy":"structural_sample_graph_nullable_life_estimates_complete_firm_rank_or_unknown_role",
        "aggregate_policy":"all_applicable_population_samples_and_estimates_or_null"}


def _exact(a,b):
    if type(a) is not type(b):return False
    if type(b) is dict:return a.keys()==b.keys() and all(_exact(a[k],v) for k,v in b.items())
    if type(b) is list:return len(a)==len(b) and all(_exact(x,y) for x,y in zip(a,b))
    return a==b


def demographic_version(world):
    from .native_social_availability import uses_native_social_availability
    if type(world) is not dict or type(world.get("summary",{})) is not dict:raise ValueError("demographic world/summary object required")
    keys=("demographic_agent_model","individual_life_event_model")
    present=[key in world for key in keys]
    own=None
    if any(present):
        if not all(present):raise ValueError("complete own demographic/life declarations required")
        old=(_demographic_agent_model(),_individual_life_event_model());new=(demographic_model_v2(),life_model_v2())
        own=1 if all(_exact(world[k],m) for k,m in zip(keys,old)) else 2 if all(_exact(world[k],m) for k,m in zip(keys,new)) else None
        if own is None:raise ValueError("unknown or mixed own demographic/life models")
        if not all(_exact(world.get("summary",{}).get(k),world[k]["model_type"]) for k in keys):raise ValueError("demographic own summary identity mismatch")
    native=uses_native_social_availability(world)
    if own is not None and (own==2)!=native:raise ValueError("demographic native family mismatch; explicit upgrade required")
    version=own or (2 if native else 1)
    if own is None and version==2:
        if (any(k in world for k in COLLECTIONS) or any(k in world["summary"] for k in SUMMARY_FIELDS)
            or any(any(k in r for k in POPULATION_ANNOTATIONS) for r in world["population_regions"])
            or any(any(k in r for k in POLITICAL_ANNOTATIONS) for r in world["political_regions"])):
            raise ValueError("undeclared demographic outputs require complete audited clearing")
    if version==1:
        summary_markers=("demographic_summary_estimate_availability","individual_summary_estimate_availability",
            "firm_selection_complete","firm_candidate_sector_count","firm_unavailable_sector_count",
            "individual_sampling_complete","individual_sampling_unavailable_region_ids","individual_sampling_known_zero_region_ids")
        population_markers=("demographic_estimate_availability","individual_sampling_available","individual_sampling_status")
        political_markers=("firm_candidate_sector_coverage","firm_selection_complete")
        def rows_have(table,markers):
            return any(type(r) is dict and any(k in r for k in markers) for r in world.get(table,[]))
        if (any(k in world.get("summary",{}) for k in summary_markers)
            or rows_have("population_regions",population_markers)
            or rows_have("political_regions",political_markers)
            or any(rows_have(key,("estimate_availability","role_available")) for key in COLLECTIONS)
            or any(type(step) is dict and "estimate_availability" in step
                for r in world.get("demographic_agent_histories",[]) if type(r) is dict
                for step in r.get("steps",[]))):
            raise ValueError("availability mirrors require demographic2")
    return version


def require_demographic_sources(world):
    from .history_economy_validation import validate_history_economy_replay
    from .logistics_availability_validation import validate_logistics_availability
    for audit in (validate_history_economy_replay,validate_logistics_availability):
        if audit(world):raise ValueError("independent history/economy/logistics2 source replay required")
    # Reject historical inputs even if they pass the historical public audit.
    if world["population_history_model"]["model_type"]!="causal_era_snapshot_logistic_migration_conflict_population_history_v2":
        raise ValueError("population-history2 required")
    regions={r["id"] for r in world["political_regions"]}
    for rows,key in ((world["population_regions"],"region_id"),(world["economy_histories"],"region_id"),(world["logistics_networks"],"region_id")):
        if len(rows)!=len(regions) or {r[key] for r in rows}!=regions:raise ValueError("complete demographic region source coverage required")
    if not world["historical_eras"] and regions:raise ValueError("actual era grid required")


def _add_map(record,fields):
    record["estimate_availability"]={k:record[k] is not None for k in fields}


def expected_demographic_availability(payload):
    households,firms,histories,pa,ra,summary=_replay_aggregate_numeric(payload)
    for row in households:_add_map(row,HOUSEHOLD_ESTIMATES)
    for row in firms:_add_map(row,FIRM_ESTIMATES)
    for row in histories:
        _add_map(row,HISTORY_ESTIMATES)
        for step in row["steps"]:_add_map(step,STEP_ESTIMATES)
    economy_by_region={e["region_id"]:e["steps"][-1] for e in payload["economy_histories"]}
    sectors=(("agriculture","agricultural_output_index"),("resource","resource_output_index"),("trade","trade_output_index"),("urban_services","urban_services_index"),("administration","administration_cost_index"))
    for r,annotations in ra.items():
        final=economy_by_region[r]
        coverage=[{"sector":sector,"sector_index":i,"selection_available":final[key] is not None,"selected":None if final[key] is None else final[key]>0.0} for i,(sector,key) in enumerate(sectors)]
        annotations["firm_candidate_sector_coverage"]=coverage
        annotations["firm_selection_complete"]=all(x["selection_available"] for x in coverage)
    for annotations in pa.values():annotations["demographic_estimate_availability"]={"representative_household_population":annotations["representative_household_population"] is not None}
    complete=all(a["firm_selection_complete"] for a in ra.values())
    if not complete:
        for key in ("total_firm_employment_capacity","mean_firm_productivity_index","mean_firm_market_dependency_index","mean_firm_supply_chain_risk_index"):summary[key]=None
    summary.update({"firm_selection_complete":complete,"firm_candidate_sector_count":len(sectors)*len(ra),
        "firm_unavailable_sector_count":sum(not x["selection_available"] for a in ra.values() for x in a["firm_candidate_sector_coverage"]),
        "demographic_summary_estimate_availability":{k:summary[k] is not None for k in AGGREGATE_ESTIMATES}})
    people,events,life_summary=_replay_individual_numeric(payload,households,firms,pa)
    for row in people:
        _add_map(row,PERSON_ESTIMATES);row["role_available"]=row["role"] is not None
    for row in events:_add_map(row,EVENT_ESTIMATES)
    regions={p["id"]:p["region_id"] for p in payload["population_regions"]}
    unavailable=[regions[i] for i,a in sorted(pa.items()) if not a["individual_sampling_available"]]
    zero=[regions[i] for i,a in sorted(pa.items()) if a["individual_sampling_status"]=="known_zero_population"]
    if unavailable:
        for k in LIFE_ESTIMATES:life_summary[k]=None
    life_summary.update({"individual_sampling_complete":not unavailable,"individual_sampling_unavailable_region_ids":unavailable,
        "individual_sampling_known_zero_region_ids":zero,"individual_summary_estimate_availability":{k:life_summary[k] is not None for k in LIFE_ESTIMATES}})
    return {"household_cohorts":households,"firm_agents":firms,"demographic_agent_histories":histories,"individual_agents":people,"individual_life_events":events,
        "population_annotations":pa,"political_annotations":ra,"summary":{**summary,**life_summary}}


def _projection(actual,expected):
    """Only parent-owned record fields; nested availability/ID lists are exact."""
    if type(actual) is not dict:return False
    return all(k in actual and _exact(actual[k],v) for k,v in expected.items())


def validate_demographic_availability(world):
    try:
        if demographic_version(world)!=2 or "demographic_agent_model" not in world:raise ValueError("declared demographic2 required")
        require_demographic_sources(world)
        expected=expected_demographic_availability(world)
        for key in COLLECTIONS:
            actual=world.get(key);wanted=expected[key]
            if type(actual) is not list or len(actual)!=len(wanted) or not all(_projection(a,b) for a,b in zip(actual,wanted)):raise ValueError("demographic record mismatch")
        if not _projection(world["summary"],expected["summary"]):raise ValueError("demographic summary mismatch")
        for table,annotations,key in (("population_regions","population_annotations","id"),("political_regions","political_annotations","id")):
            actual={r[key]:r for r in world[table]}
            for ident,wanted in expected[annotations].items():
                if not _projection(actual[ident],wanted):raise ValueError("demographic source annotation mismatch")
        return []
    except (ValueError,TypeError,KeyError,IndexError,OverflowError,ZeroDivisionError,AttributeError):
        return ["demographic availability or independent life-event replay invalid"]
