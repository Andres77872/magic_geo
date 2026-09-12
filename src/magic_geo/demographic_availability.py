"""Nullable representative demographic equations; parent replay is external.

No unknown estimate is replaced with a numerical sentinel. All returned
annotations are private until the public wrapper has independently audited them.
"""
from __future__ import annotations
import math


def _calc(function, *values):
    if any(v is None for v in values): return None
    result=function(*values)
    if result is not None and not math.isfinite(result):
        raise ValueError("demographic estimate is not representable")
    return result


def _clamp(x,low=0.0,high=1.0):
    return _calc(lambda v:max(low,min(high,v)),x)


def _record(identity,estimates):
    return {**identity,**{k:_calc(lambda v:round(v,8 if k=="fertility_rate_per_year" else 6),x) for k,x in estimates.items()},
        "estimate_availability":{k:v is not None for k,v in estimates.items()}}


def _aggregate(values, *, mean=False, complete=True):
    if not complete or any(v is None for v in values):return None
    total=sum(values,0.0)
    return _calc(lambda v:v/max(1,len(values)) if mean else v,total)


def _market_pressure(world):
    result={p["id"]:0.0 for p in world["political_regions"]}
    for exchange in world["market_exchanges"]:
        value=_calc(lambda d,a,f:_clamp(d*.62+a*.18+f*.20),
                    _clamp(exchange["disruption_risk_index"]),_clamp(exchange["market_access_index"]),exchange["friction"])
        for key in ("region_from","region_to"):
            r=exchange[key];result[r]=_calc(max,result[r],value)
    return result


def aggregate_agents(world):
    """Return cohorts, firms, complete history slots, and owned annotations."""
    from .demographic_agents import _cohort_specs
    populations=sorted(world["population_regions"],key=lambda p:p["id"])
    history_by_id={h["population_region_id"]:h for h in world["population_histories"]}
    economies={e["region_id"]:e for e in world["economy_histories"]}
    networks={n["region_id"]:n for n in world["logistics_networks"]}
    regions={r["id"]:r for r in world["political_regions"]}
    settlements={r:[] for r in regions}
    for s in world["settlements"]:settlements[s["region_id"]].append(s["id"])
    for values in settlements.values():values.sort()
    pressures=_market_pressure(world)
    households,firms,histories=[],[],[]
    pa,ra={},{}
    raw_households,raw_firms,raw_histories=[],[],[]
    for p in populations:
        region=p["region_id"];h=history_by_id[p["id"]];e=economies[region]["steps"][-1];n=networks[region]
        final=_calc(lambda x:max(0.0,x),h["final_population"])
        urban=_clamp(p["urbanization_fraction"]);balance=p["migration_balance"];pressure=_clamp(p["population_pressure"])
        hazard=_clamp(p["hazard_mortality_index"]);water=_clamp(p["water_security_index"])
        food=_clamp(e["food_security_index"]);prosperity=_clamp(e["prosperity_index"]);dependency=_clamp(e["trade_dependency_index"])
        resilience=_clamp(n["logistics_resilience_index"])
        fractions=None if any(v is None for v in (urban,balance,pressure)) else _cohort_specs(urban,balance,pressure)
        allocated=0.0;ids=[]
        for index,(kind,size,modifier) in enumerate((("rural_household",5.1,.04),("urban_household",3.8,-.02),("mobile_household",4.2,.10))):
            fraction=fractions[index][1] if fractions is not None else None
            # The residual third share depends on the previous raw allocations.
            value=0.0 if final==0.0 else _calc(lambda p,a:max(0.0,p-a),final,allocated) if index==2 else _calc(lambda p,f:max(0.0,p*f),final,fraction)
            if index<2:allocated=_calc(lambda a,b:a+b,allocated,value)
            vulnerability=_calc(lambda h,p,w,f,m:_clamp(h*.30+p*.24+(1.0-w)*.20+(1.0-f)*.14+m*.08+modifier),hazard,pressure,water,food,pressures[region])
            migration=_calc(lambda b,p,v,r:_clamp(abs(b)*.38+p*.18+v*.22+(1.0-r)*.14+(.12 if kind=="mobile_household" else 0.0)),balance,pressure,vulnerability,resilience)
            consumption=_calc(lambda p,f,s,d,v:_clamp(p*.34+(1.0-f)*.24+(1.0-s)*.18+d*.14+v*.10),pressure,food,prosperity,dependency,vulnerability)
            income=_calc(lambda s,v,u,r:_clamp(s*.42+(1.0-v)*.22+u*.16+r*.20),prosperity,vulnerability,urban,resilience)
            labor=_calc(lambda s,v:_clamp(.43+s*.18-v*.12+(.07 if kind=="urban_household" else 0.0)),prosperity,vulnerability)
            fertility=_calc(lambda u,p,v:max(0.0,.0007+(1.0-u)*.0007+p*.0004-v*.00025),urban,pressure,vulnerability)
            mortality=_calc(lambda h,v,p:_clamp(h*.44+v*.38+p*.18),hazard,vulnerability,pressure)
            estimates={"population":value,"household_count":_calc(lambda p:p/max(1.0,size),value),"average_household_size":size,
                "urbanization_fraction":urban,"water_security_index":water,"food_security_index":food,"income_index":income,
                "consumption_pressure_index":consumption,"vulnerability_index":vulnerability,"migration_propensity_index":migration,
                "fertility_rate_per_year":fertility,"mortality_risk_index":mortality,"labor_participation_index":labor}
            cid=len(households);ids.append(cid)
            households.append(_record({"id":cid,"population_region_id":p["id"],"region_id":region,"culture_region_id":p["culture_region_id"],
                "language_region_id":p["language_region_id"],"cohort_type":kind},estimates));raw_households.append(estimates)
        represented=_aggregate([households[c]["population"] for c in ids])
        pa[p["id"]]={"household_cohort_ids":ids,"household_cohort_count":len(ids),
            "representative_household_population":_calc(lambda x:round(x,6),represented),
            "demographic_estimate_availability":{"representative_household_population":represented is not None}}
    sectors=(("agriculture","agricultural_output_index",.30),("resource","resource_output_index",.44),("trade","trade_output_index",.82),
             ("urban_services","urban_services_index",.56),("administration","administration_cost_index",.24))
    for economy in sorted(world["economy_histories"],key=lambda e:e["region_id"]):
        region=economy["region_id"];e=economy["steps"][-1];n=networks[region]
        population=_calc(lambda p:max(0.0,p),e["population"]);gross=_calc(lambda g:max(1.0,g),e["gross_output_index"])
        prosperity=_clamp(e["prosperity_index"]);dependency=_clamp(e["trade_dependency_index"]);stability=_clamp(e["stability_index"])
        burden=_clamp(e["military_burden_index"]);resilience=_clamp(n["logistics_resilience_index"]);chokepoint=_clamp(n["chokepoint_exposure_index"])
        ids=[];coverage=[]
        for index,(sector,key,base) in enumerate(sectors):
            output=e[key]
            coverage.append({"sector":sector,"sector_index":index,"selection_available":output is not None,"selected":None if output is None else output>0.0})
            if output is None or output<=0.0:continue
            share=_calc(lambda o,g:_clamp(o/g),output,gross)
            market=_calc(lambda d,s:_clamp(base*.52+d*.34+s*.14),dependency,share)
            productivity=_calc(lambda o,p,s,r:_clamp(o*.42+p*.30+s*.18+r*.10),share,prosperity,stability,resilience)
            risk=_calc(lambda c,m,r,b:_clamp(c*.32+m*.26+(1.0-r)*.24+b*.18),chokepoint,market,resilience,burden)
            employment=_calc(lambda p,s,r:p*s*(.30+r*.28),population,share,productivity)
            tax=_calc(lambda o,m,r:o*(.07+m*.025)*(1.0-r*.16),output,market,risk)
            estimates={"output_index":max(0.0,output),"employment_capacity":employment,
                "wage_index":_calc(lambda p,r,s:_clamp(p*.45+r*.35+(1.0-s)*.20),prosperity,productivity,risk),
                "productivity_index":productivity,"market_dependency_index":market,
                "capital_stock_index":_calc(lambda o,p,r:_clamp(o/260.0*.48+p*.26+r*.26),output,prosperity,resilience),
                "supply_chain_risk_index":risk,"tax_contribution_index":tax}
            settlement=regions[region]["capital_settlement_id"] if index==0 or not settlements[region] else settlements[region][index%len(settlements[region])]
            fid=len(firms);ids.append(fid)
            firms.append(_record({"id":fid,"region_id":region,"population_region_id":economy["population_region_id"],"settlement_id":settlement,"sector":sector},estimates));raw_firms.append(estimates)
        ra[region]={"firm_agent_ids":ids,"firm_agent_count":len(ids),"firm_candidate_sector_coverage":coverage,
            "firm_selection_complete":all(c["selection_available"] for c in coverage)}
    for p in populations:
        h=history_by_id[p["id"]];region=p["region_id"];ids=pa[p["id"]]["household_cohort_ids"]
        weights=[households[c]["population"] for c in ids]
        numerator=_aggregate([_calc(lambda a,b:a*b,households[c]["labor_participation_index"],households[c]["population"]) for c in ids])
        labor=_calc(lambda n,d:n/max(1.0,d),numerator,_aggregate(weights))
        steps=[]
        for index,s in enumerate(h["steps"]):
            start=_calc(lambda x:max(0.0,x),s["start_population"]);end=_calc(lambda x:max(0.0,x),s["end_population"])
            pressure=_clamp(s["pressure_index"]);hazard=_clamp(s["hazard_mortality_index"])
            loss=_calc(lambda x:max(0.0,x),s["conflict_loss"]);migration=s["migration_delta"]
            fraction=_calc(lambda l,p:_clamp(l/max(1.0,p)),loss,start)
            propensity=_calc(lambda m,s,p,h,l:_clamp(abs(m)/max(1.0,s)*8.0+p*.20+h*.18+l*.28),migration,start,pressure,hazard,fraction)
            vulnerability=_calc(lambda h,p,l,m:_clamp(h*.32+p*.26+l*.28+m*.14),hazard,pressure,fraction,propensity)
            working=_calc(lambda p,l:p*l,end,labor);dependent=_calc(lambda p,w:max(0.0,p-w),end,working)
            consumption=_calc(lambda p,d,e,v,l:_clamp(p*.42+d/max(1.0,e)*.24+v*.22+l*.12),pressure,dependent,end,vulnerability,fraction)
            estimates={"start_population":start,"end_population":end,"working_population":working,"dependent_population":dependent,
                "migration_propensity_index":propensity,"consumption_pressure_index":consumption,"vulnerability_index":vulnerability,"labor_participation_index":labor}
            steps.append(_record({"era_id":s["era_id"],"stage_index":index+1,"start_year_bp":round(s["start_year_bp"],6),"end_year_bp":round(s["end_year_bp"],6)},estimates));raw_histories.append(estimates)
        hid=len(histories)
        histories.append(_record({"id":hid,"population_region_id":p["id"],"region_id":region,"household_cohort_ids":list(ids),
            "firm_agent_ids":list(ra[region]["firm_agent_ids"]),"step_count":len(steps),"steps":steps},
            {"final_agent_population":h["final_population"],"mean_labor_participation_index":labor}))
        pa[p["id"]]["demographic_agent_history_id"]=hid
    complete_firms=all(r["firm_selection_complete"] for r in ra.values())
    estimates={"total_household_cohort_population":_aggregate([h["population"] for h in raw_households]),
        "total_firm_employment_capacity":_aggregate([f["employment_capacity"] for f in raw_firms],complete=complete_firms),
        "mean_household_resilience_index":_aggregate([_calc(lambda v:1.0-v,h["vulnerability_index"]) for h in raw_households],mean=True),
        "mean_household_migration_propensity_index":_aggregate([h["migration_propensity_index"] for h in raw_households],mean=True),
        "mean_household_consumption_pressure_index":_aggregate([h["consumption_pressure_index"] for h in raw_households],mean=True),
        "mean_firm_productivity_index":_aggregate([f["productivity_index"] for f in raw_firms],mean=True,complete=complete_firms),
        "mean_firm_market_dependency_index":_aggregate([f["market_dependency_index"] for f in raw_firms],mean=True,complete=complete_firms),
        "mean_firm_supply_chain_risk_index":_aggregate([f["supply_chain_risk_index"] for f in raw_firms],mean=True,complete=complete_firms),
        "mean_demographic_vulnerability_index":_aggregate([s["vulnerability_index"] for s in raw_histories],mean=True),
        "high_vulnerability_household_count":None if any(h["vulnerability_index"] is None for h in raw_households) else sum(h["vulnerability_index"]>=.65 for h in raw_households)}
    summary=_record({"household_cohort_count":len(households),"firm_agent_count":len(firms),"demographic_agent_history_count":len(histories),
        "demographic_agent_step_count":len(raw_histories),"firm_selection_complete":complete_firms,
        "firm_candidate_sector_count":sum(len(r["firm_candidate_sector_coverage"]) for r in ra.values()),
        "firm_unavailable_sector_count":sum(not c["selection_available"] for r in ra.values() for c in r["firm_candidate_sector_coverage"])},estimates)
    summary["demographic_summary_estimate_availability"]=summary.pop("estimate_availability")
    return {"household_cohorts":households,"firm_agents":firms,"demographic_agent_histories":histories,
        "population_annotations":pa,"political_annotations":ra,"summary":summary}


def individual_agents(world, aggregate):
    from .demographic_agents import _person_name, ROLE_SEQUENCE
    households=aggregate["household_cohorts"];firms=aggregate["firm_agents"]
    pa=aggregate["population_annotations"];ra=aggregate["political_annotations"]
    histories={h["population_region_id"]:h for h in world["population_histories"]}
    eras=sorted(world["historical_eras"],key=lambda e:(-float(e["start_year_bp"]),e["id"]))
    people,events=[],[]
    unavailable,known_zero=[],[]
    raw_lifespans,raw_transfers=[],[]
    event_counts={k:0 for k in ("birth","death","marriage","property_transfer")}
    def event(identity,estimates):
        eid=len(events);events.append(_record({"id":eid,**identity},estimates))
        people[identity["person_id"]]["event_ids"].append(eid)
        event_counts[identity["event_type"]]+=1
    for p in sorted(world["population_regions"],key=lambda p:p["id"]):
        pid,region,culture=p["id"],p["region_id"],p["culture_region_id"]
        represented=histories[pid]["final_population"]
        pa[pid]["individual_sampling_available"]=represented is not None
        pa[pid]["individual_sampling_status"]=("unavailable_population" if represented is None else "known_zero_population" if represented==0.0 else "sampled_positive_population")
        pa[pid]["individual_agent_ids"]=[];pa[pid]["individual_agent_count"]=0
        if represented is None:unavailable.append(region);continue
        if represented==0.0:known_zero.append(region);continue
        cohort_ids=pa[pid]["household_cohort_ids"]
        selected=[firms[i] for i in ra[region]["firm_agent_ids"]]
        ranking=ra[region]["firm_selection_complete"] and all(f["employment_capacity"] is not None for f in selected)
        dominant=(max(selected,key=lambda f:f["employment_capacity"])["sector"] if selected else "subsistence") if ranking else None
        region_people=[]
        for index in range(min(6,max(2,len(cohort_ids)*2))):
            cohort_id=cohort_ids[index%len(cohort_ids)];cohort=households[cohort_id]
            cohort_population=_calc(lambda x:max(1.0,x),cohort["population"])
            household_count=_calc(lambda x:max(1.0,x),cohort["household_count"])
            fertility=_calc(lambda x:max(0.0,x),cohort["fertility_rate_per_year"])
            mortality=_clamp(cohort["mortality_risk_index"]);vulnerability=_clamp(cohort["vulnerability_index"])
            migration=_clamp(cohort["migration_propensity_index"]);income=_clamp(cohort["income_index"])
            birth_era=eras[index%len(eras)];death_era=eras[-1]
            expectancy=_calc(lambda m,v,i:max(18.0,78.0-m*26.0-v*18.0+i*10.0),mortality,vulnerability,income)
            birth=max(float(death_era["end_year_bp"]),float(birth_era["start_year_bp"])-16.0-index*7.0)
            death=_calc(lambda l:max(float(death_era["end_year_bp"]),birth-l),expectancy)
            share=_calc(lambda p,h:p/h,cohort_population,household_count)
            property_value=_calc(lambda s,i,v:max(0.0,s*(.24+i*.46)*(1.0-v*.22)),share,income,vulnerability)
            person_id=len(people);role=ROLE_SEQUENCE[(region+index)%len(ROLE_SEQUENCE)]
            if role=="farmer" and index%3==0:
                role=dominant if dominant!="agriculture" else role
            lifespan=_calc(lambda d:max(0.0,birth-d),death)
            people.append(_record({"id":person_id,"population_region_id":pid,"region_id":region,"household_cohort_id":cohort_id,
                "culture_region_id":culture,"language_region_id":p["language_region_id"],"name":_person_name(region,index,culture),
                "role":role,"role_available":role is not None,"married_person_id":-1,"parent_person_ids":[],"child_person_ids":[],"event_ids":[],"event_count":0},
                {"birth_year_bp":birth,"death_year_bp":death,"lifespan_years":lifespan,"property_value_index":property_value,
                 "mobility_index":migration,"vulnerability_index":vulnerability}))
            region_people.append(person_id);raw_lifespans.append(lifespan)
            common={"person_id":person_id,"population_region_id":pid,"region_id":region,"household_cohort_id":cohort_id}
            event({**common,"related_person_id":-1,"era_id":birth_era["id"],"event_type":"birth"},
                {"year_bp":birth,"property_value_index":0.0,"demographic_pressure_index":_calc(lambda f,m:_clamp(f*320.0+m*.18),fertility,migration),
                 "mortality_risk_index":mortality,"inheritance_fraction":0.0})
            if index>=2:
                parents=[region_people[index-2]]
                if index>=3:parents.append(region_people[index-3])
                people[person_id]["parent_person_ids"]=parents
                for parent in parents:people[parent]["child_person_ids"].append(person_id)
            if index%2==1:
                spouse=region_people[index-1]
                marriage=_calc(lambda d,v:max(d,birth-22.0-v*6.0),death,vulnerability)
                people[person_id]["married_person_id"]=spouse;people[spouse]["married_person_id"]=person_id
                for participant,related in ((person_id,spouse),(spouse,person_id)):
                    event({**common,"person_id":participant,"related_person_id":related,"household_cohort_id":people[participant]["household_cohort_id"],"era_id":birth_era["id"],"event_type":"marriage"},
                        {"year_bp":marriage,"property_value_index":0.0,"demographic_pressure_index":_calc(lambda m,v:_clamp(m*.26+v*.20),migration,vulnerability),
                         "mortality_risk_index":mortality,"inheritance_fraction":0.0})
            transfer_year=_calc(lambda d,l:max(d,birth-max(1.0,l*.72)),death,expectancy)
            recipient=region_people[index-2] if index>=2 else -1
            fraction=.48 if recipient>=0 else .20
            transfer=_calc(lambda p:p*fraction,property_value);raw_transfers.append(transfer)
            event({**common,"related_person_id":recipient,"era_id":death_era["id"],"event_type":"property_transfer"},
                {"year_bp":transfer_year,"property_value_index":transfer,"demographic_pressure_index":_calc(lambda m,v:_clamp(m*.22+v*.24),migration,vulnerability),
                 "mortality_risk_index":mortality,"inheritance_fraction":fraction})
            event({**common,"related_person_id":-1,"era_id":death_era["id"],"event_type":"death"},
                {"year_bp":death,"property_value_index":0.0,"demographic_pressure_index":_calc(lambda v,m:_clamp(v*.42+m*.38),vulnerability,mortality),
                 "mortality_risk_index":mortality,"inheritance_fraction":0.0})
        for person_id in region_people:people[person_id]["event_count"]=len(people[person_id]["event_ids"])
        pa[pid]["individual_agent_ids"]=region_people;pa[pid]["individual_agent_count"]=len(region_people)
    summary=_record({"individual_agent_count":len(people),"individual_life_event_count":len(events),
        "individual_birth_event_count":event_counts["birth"],"individual_death_event_count":event_counts["death"],
        "individual_marriage_event_count":event_counts["marriage"],"property_transfer_event_count":event_counts["property_transfer"],
        "individual_sampling_complete":not unavailable,"individual_sampling_unavailable_region_ids":unavailable,"individual_sampling_known_zero_region_ids":known_zero},
        {"mean_individual_lifespan_years":_aggregate(raw_lifespans,mean=True,complete=not unavailable),
         "total_property_transfer_value_index":_aggregate(raw_transfers,complete=not unavailable)})
    summary["individual_summary_estimate_availability"]=summary.pop("estimate_availability")
    return {"individual_agents":people,"individual_life_events":events,"summary":summary}


def _demographic_model_v2():
    from .demographic_agents import _demographic_agent_model
    return {**_demographic_agent_model(),"model_type":"causal_population_economy_logistics_household_firm_demographic_history_v2",
        "source_population_region_model":"causal_area_weighted_capacity_occupancy_population_regions_v2",
        "source_population_history_model":"causal_era_snapshot_logistic_migration_conflict_population_history_v2",
        "source_economy_history_model":"causal_population_trade_conflict_treasury_economy_history_v2",
        "source_logistics_exchange_model":"causal_region_route_trade_economy_logistics_exchange_v2",
        "household_model":"three_template_nullable_normalized_population_cohorts_v2",
        "firm_selection_policy":"known_positive_firms_with_explicit_unknown_candidate_sector_coverage",
        "availability_policy":"typed_per_field_null_unknown_no_parent_default_substitution",
        "aggregate_policy":"complete_candidate_scope_and_complete_estimates_or_null_no_partial_renormalization"}


def _life_model_v2():
    from .demographic_agents import _individual_life_event_model
    return {**_individual_life_event_model(),"model_type":"causal_household_firm_era_sampled_individual_life_event_graph_v2",
        "source_demographic_agent_model":"causal_population_economy_logistics_household_firm_demographic_history_v2",
        "source_historical_event_model":"causal_region_culture_language_trade_site_timeline_v2",
        "sampling_model":"six_positive_population_template_people_zero_complete_empty_unknown_unavailable_v2",
        "availability_policy":"structural_sample_graph_nullable_life_estimates_complete_firm_rank_or_unknown_role",
        "aggregate_policy":"all_applicable_population_samples_and_estimates_or_null"}


def enrich_demographic_availability(world):
    from .demographic_availability_validation import (demographic_version,require_demographic_sources,
        validate_demographic_availability,COLLECTIONS)
    if demographic_version(world)!=2:raise ValueError("demographic2 source required")
    require_demographic_sources(world)
    if "demographic_agent_model" in world:
        errors=validate_demographic_availability(world)
        if errors:raise ValueError(errors[0])
        return world
    aggregate=aggregate_agents(world);life=individual_agents(world,aggregate)
    summary={**aggregate["summary"],**life["summary"]}
    models={"demographic_agent_model":_demographic_model_v2(),"individual_life_event_model":_life_model_v2()}
    summary.update({k:v["model_type"] for k,v in models.items()})
    staged={**world,**models,"summary":{**world["summary"],**summary},
        **{k:aggregate[k] if k in aggregate else life[k] for k in COLLECTIONS},
        "population_regions":[{**p,**aggregate["population_annotations"][p["id"]]} for p in world["population_regions"]],
        "political_regions":[{**r,**aggregate["political_annotations"][r["id"]]} for r in world["political_regions"]]}
    errors=validate_demographic_availability(staged)
    if errors:raise ValueError(errors[0])
    for key in COLLECTIONS:world[key]=staged[key]
    world.update(models);world["summary"].update(summary)
    for p in world["population_regions"]:p.update(aggregate["population_annotations"][p["id"]])
    for r in world["political_regions"]:r.update(aggregate["political_annotations"][r["id"]])
    return world
