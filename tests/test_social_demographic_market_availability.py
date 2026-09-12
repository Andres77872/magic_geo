"""Availability boundaries on retained native-stage sources, without generation.

Public controls use the real independent parent validators. Deliberately altered
scalar fragments call the separate producer/oracle equation bodies only; those
fragments do not claim a valid full parent world or full climate certificate.
"""
from copy import deepcopy
from functools import lru_cache
from unittest import TestCase
from unittest.mock import patch
import math

from magic_geo import demographic_agents as demographic
from magic_geo import demographic_agents_validation as demographic_public
from magic_geo import demographic_availability as d
from magic_geo import demographic_availability_validation as da
from magic_geo import market_clearing as market
from magic_geo import market_clearing_validation as market_public
from magic_geo import market_availability as m
from magic_geo import market_availability_validation as ma
from support.native_campaign_worlds import campaign_public_world
from support.legacy_human_water_worlds import legacy_human_water_world_readonly


@lru_cache(None)
def source(name="healthy"):
    return campaign_public_world(name)


@lru_cache(None)
def demographic_world(name="healthy"):
    world=deepcopy(source(name));demographic.enrich_world_with_demographic_agents(world)
    assert demographic_public.validate_demographic_agents_replay(world)==[]
    return world


@lru_cache(None)
def completed(name="healthy"):
    world=deepcopy(demographic_world(name));market.enrich_world_with_market_clearing(world)
    assert market_public.validate_market_clearing_replay(world)==[]
    return world


def changed(v):
    if type(v) is bool:return not v
    if v is None:return 0.0
    if type(v) in (int,float):return v+1
    if type(v) is str:return v+"_wrong"
    if type(v) is list:return v[:-1] if v else ["extra"]
    if type(v) is dict:return {**v,"extra":True}
    raise AssertionError(v)


def project(value,template):
    """Historical fields only, preserving their exact nesting and values."""
    if type(template) is dict:return {k:project(value[k],v) for k,v in template.items()}
    if type(template) is list:
        assert len(value)==len(template)
        return [project(x,y) for x,y in zip(value,template)]
    return value


def demographic_fragment(world):
    aggregate=d.aggregate_agents(world);life=d.individual_agents(world,aggregate)
    result={**aggregate,**life,"summary":{**aggregate["summary"],**life["summary"]}}
    assert result==da.expected_demographic_availability(world)
    return result


def market_fragment(world):
    staged=deepcopy(world);m._build_market_numeric(staged);m._decorate_market_estimates(staged)
    expected=ma.expected_market_availability(world)
    for key in ma.FIELD_SCHEMAS:assert staged[key]==expected[key]
    for key,value in expected["summary"].items():assert staged["summary"][key]==value
    for table,fields,name in (("routes",ma.ROUTE_ANNOTATIONS,"route_annotations"),("market_exchanges",ma.EXCHANGE_ANNOTATIONS,"exchange_annotations")):
        for row in staged[table]:assert {k:row[k] for k in fields if k in row}==expected[name][row["id"]]
    return staged


class RetainedSocialAvailability(TestCase):
    def test_public_healthy_and_mixed_complete_parent_chains(self):
        for name in ("healthy","mixed"):
            with self.subTest(name=name):
                world=completed(name)
                self.assertEqual(demographic_public.validate_demographic_agents_replay(world),[])
                self.assertEqual(market_public.validate_market_clearing_replay(world),[])
                self.assertEqual(len(world["household_cohorts"]),6)
                self.assertEqual([len(r["firm_candidate_sector_coverage"]) for r in world["political_regions"]],[5,5])
                self.assertEqual([[s["era_id"] for s in r["steps"]] for r in world["demographic_agent_histories"]],[[0,1,2,3]]*2)
                self.assertEqual(len(world["market_clearing_records"]),10)
                self.assertEqual(len(world["market_price_iterations"]),30)
                self.assertEqual([len(r["steps"]) for r in world["market_inventory_histories"]],[3]*10)
        healthy=completed();mixed=completed("mixed")
        self.assertEqual([len(healthy[k]) for k in ("firm_agents","individual_agents","individual_life_events","market_agent_orders")],[10,12,48,70])
        self.assertEqual([len(mixed[k]) for k in ("firm_agents","individual_agents","individual_life_events","market_agent_orders")],[0,0,0,30])
        self.assertTrue(healthy["summary"]["market_order_selection_complete"])
        self.assertFalse(mixed["summary"]["market_order_selection_complete"])
        self.assertIsNone(mixed["summary"]["total_firm_employment_capacity"])
        self.assertIsNone(mixed["summary"]["total_property_transfer_value_index"])
        self.assertTrue(all(o["agent_type"]=="household_cohort" for o in mixed["market_agent_orders"]))
        self.assertTrue(all(r["requested_volume_index"] is not None for r in mixed["market_clearing_records"]))
        self.assertTrue(all(r["high_inventory_stress"] is None for r in mixed["market_inventory_histories"]))

    def test_healthy_same_input_original_equation_parity(self):
        old=deepcopy(source());demographic._enrich_demographic_agents_v1(old)
        new=demographic_world()
        for key in da.COLLECTIONS:self.assertEqual(project(new[key],old[key]),old[key])
        for key in da.SUMMARY_FIELDS:
            if key in old["summary"] and not key.endswith("_model"):self.assertEqual(new["summary"][key],old["summary"][key])
        market._enrich_market_clearing_v1(old);new=completed()
        for key in ma.FIELD_SCHEMAS:self.assertEqual(project(new[key],old[key]),old[key])
        for key in ma.SUMMARY_FIELDS:
            if key in old["summary"] and not key.endswith("_model"):self.assertEqual(new["summary"][key],old["summary"][key])

    def test_complete_historical_archive_public_parity(self):
        world=deepcopy(legacy_human_water_world_readonly())
        self.assertEqual(demographic_public.validate_demographic_agents_replay(world),[])
        self.assertEqual(market_public.validate_market_clearing_replay(world),[])
        before=deepcopy(world)
        demographic.enrich_world_with_demographic_agents(world);market.enrich_world_with_market_clearing(world)
        self.assertEqual(world,before)

    def test_parent_values_and_maps_preserved(self):
        for name in ("healthy","mixed"):
            before=source(name);after=completed(name)
            for key,value in before.items():
                if key=="summary":self.assertEqual(project(after[key],value),value)
                elif key in ("population_regions","political_regions","routes","market_exchanges"):
                    self.assertEqual(project(after[key],value),value)
                else:self.assertEqual(after[key],value)
            for table in ("population_regions","logistics_networks","market_exchanges"):
                self.assertEqual([r.get("estimate_availability") for r in after[table]],[r.get("estimate_availability") for r in before[table]])

    def test_valid_reenrichment_preserves_descendant_annotations(self):
        world=deepcopy(completed())
        for table in ("household_cohorts","firm_agents","individual_agents","market_clearing_records"):
            world[table][0]["future_owned_annotation"]={"valid":True}
        before=deepcopy(world)
        demographic.enrich_world_with_demographic_agents(world);market.enrich_world_with_market_clearing(world)
        self.assertEqual(world,before)

    def test_invalid_owned_reenrichment_rejects_atomically(self):
        for producer,table,key in ((demographic.enrich_world_with_demographic_agents,"household_cohorts","population"),(market.enrich_world_with_market_clearing,"market_clearing_records","requested_volume_index")):
            world=deepcopy(completed());world[table][0][key]+=1;world[table][0]["descendant"]=[1,2]
            before=deepcopy(world)
            with self.assertRaises(ValueError):producer(world)
            self.assertEqual(world,before)

    def test_poisoned_private_producer_outputs_are_not_committed(self):
        original=d.aggregate_agents
        def poison(world):
            result=original(world);result["household_cohorts"][0]["population"]+=1;return result
        world=deepcopy(source());before=deepcopy(world)
        with patch.object(d,"aggregate_agents",side_effect=poison),self.assertRaises(ValueError):demographic.enrich_world_with_demographic_agents(world)
        self.assertEqual(world,before)
        original_market=m._build_market_numeric
        def poison_market(world):
            original_market(world);world["market_price_iterations"][0]["price_index"]+=1
        world=deepcopy(demographic_world());before=deepcopy(world)
        with patch.object(m,"_build_market_numeric",side_effect=poison_market),self.assertRaises(ValueError):market.enrich_world_with_market_clearing(world)
        self.assertEqual(world,before)

    def test_all_owned_records_and_steps_replayed(self):
        for keys,validator in ((da.COLLECTIONS,da.validate_demographic_availability),(ma.FIELD_SCHEMAS,ma.validate_market_availability)):
            for table in keys:
                for nested in (False,True) if "steps" in completed()[table][0] else (False,):
                    template=completed()[table][0]
                    if nested:template=template["steps"][0]
                    for key in template:
                        for op in ("change","delete"):
                            with self.subTest(table=table,nested=nested,key=key,op=op):
                                world=deepcopy(completed());row=world[table][0]
                                if nested:row=row["steps"][0]
                                if op=="delete":del row[key]
                                else:row[key]=changed(row[key])
                                self.assertTrue(validator(world))

    def test_owned_summaries_annotations_and_models_replayed(self):
        groups=((da,da.validate_demographic_availability,("demographic_agent_model","individual_life_event_model")),(ma,ma.validate_market_availability,("market_clearing_model",)))
        for module,validator,models in groups:
            for table,keys in [("summary",module.SUMMARY_FIELDS),*((model,completed()[model]) for model in models)]:
                for key in keys:
                    with self.subTest(table=table,key=key):
                        world=deepcopy(completed());world[table][key]=changed(world[table][key]);self.assertTrue(validator(world))
        for table,keys,validator in (("population_regions",da.POPULATION_ANNOTATIONS,da.validate_demographic_availability),("political_regions",da.POLITICAL_ANNOTATIONS,da.validate_demographic_availability),("routes",ma.ROUTE_ANNOTATIONS,ma.validate_market_availability),("market_exchanges",ma.EXCHANGE_ANNOTATIONS,ma.validate_market_availability)):
            for key in keys:
                with self.subTest(table=table,key=key):
                    world=deepcopy(completed());world[table][0][key]=changed(world[table][0][key]);self.assertTrue(validator(world))

    def test_every_estimate_flag_is_strict_and_missing_never_zero(self):
        for name in ("healthy","mixed"):
            for keys,validator in ((da.COLLECTIONS,da.validate_demographic_availability),(ma.FIELD_SCHEMAS,ma.validate_market_availability)):
                for table in keys:
                    if not completed(name)[table]:continue
                    for nested in (False,True) if "steps" in completed(name)[table][0] else (False,):
                        row=completed(name)[table][0]
                        if nested:row=row["steps"][0]
                        for key in row["estimate_availability"]:
                            with self.subTest(name=name,table=table,nested=nested,key=key):
                                world=deepcopy(completed(name));obj=world[table][0]
                                if nested:obj=obj["steps"][0]
                                obj["estimate_availability"][key]=int(obj["estimate_availability"][key]);self.assertTrue(validator(world))
                        key=next(iter(row["estimate_availability"]));world=deepcopy(completed(name));obj=world[table][0]
                        if nested:obj=obj["steps"][0]
                        obj[key]=False;self.assertTrue(validator(world))

    def test_shape_nonfinite_and_parent_corruption_rejected(self):
        for table,key,validator in (("individual_agents","property_value_index",da.validate_demographic_availability),("market_clearing_records","cleared_volume_index",ma.validate_market_availability)):
            for value in (math.nan,math.inf,-math.inf,False,"0",[],{}):
                world=deepcopy(completed());world[table][0][key]=value;self.assertTrue(validator(world))
            world=deepcopy(completed());world[table]=tuple(world[table]);self.assertTrue(validator(world))
        for table,key in (("population_histories","final_population"),("economy_histories","peak_gross_output_index"),("logistics_networks","logistics_resilience_index"),("market_exchanges","tax_revenue_index")):
            for producer,base in ((demographic.enrich_world_with_demographic_agents,source()),(market.enrich_world_with_market_clearing,demographic_world())):
                with self.subTest(table=table,producer=producer.__name__):
                    world=deepcopy(base);del world[table][0][key];before=deepcopy(world)
                    with self.assertRaises(ValueError):producer(world)
                    self.assertEqual(world,before)

    def test_own_dispatch_before_parent_and_partial_mirror_rejection(self):
        for module,base,models,version in ((da,source(),("demographic_agent_model","individual_life_event_model"),da.demographic_version),(ma,demographic_world(),("market_clearing_model",),ma.market_version)):
            world=deepcopy(base);world[models[0]]={"model_type":"future"};world.pop("population_regions")
            with self.assertRaisesRegex(ValueError,"own|declarations"):version(world)
            world=deepcopy(completed())
            for key in models:del world[key];del world["summary"][key]
            with self.assertRaisesRegex(ValueError,"undeclared"):version(world)
            world=deepcopy(completed());world["summary"][models[0]]=False
            with self.assertRaisesRegex(ValueError,"identity"):version(world)

    def test_all_legacy_orphan_markers_rejected(self):
        old=legacy_human_water_world_readonly()
        paths=[("summary",k) for k in ("demographic_summary_estimate_availability","individual_summary_estimate_availability","firm_selection_complete","firm_candidate_sector_count","firm_unavailable_sector_count","individual_sampling_complete","individual_sampling_unavailable_region_ids","individual_sampling_known_zero_region_ids")]
        paths += [("population_regions",0,k) for k in ("demographic_estimate_availability","individual_sampling_available","individual_sampling_status")]
        paths += [("political_regions",0,k) for k in ("firm_candidate_sector_coverage","firm_selection_complete")]
        paths += [(key,0,"estimate_availability") for key in da.COLLECTIONS]
        paths += [("individual_agents",0,"role_available"),("demographic_agent_histories",0,"steps",0,"estimate_availability")]
        for path in paths:
            with self.subTest(path=path):
                world=deepcopy(old);row=world
                for key in path[:-1]:row=row[key]
                row[path[-1]]=True
                with self.assertRaisesRegex(ValueError,"mirrors"):da.demographic_version(world)
        paths=[("summary",k) for k in ("market_summary_estimate_availability","market_order_selection_complete","unavailable_market_order_exchange_ids")]
        paths += [(key,0,"estimate_availability") for key in ma.FIELD_SCHEMAS]
        paths += [("market_clearing_records",0,k) for k in ("order_family_availability","agent_order_selection_complete")]
        paths += [("routes",0,"market_capacity_estimate_availability"),("market_exchanges",0,"market_clearing_estimate_availability"),("market_inventory_histories",0,"steps",0,"estimate_availability")]
        for path in paths:
            with self.subTest(path=path):
                world=deepcopy(old);row=world
                for key in path[:-1]:row=row[key]
                row[path[-1]]=True
                with self.assertRaisesRegex(ValueError,"mirrors"):ma.market_version(world)


class ScopedEquationFragments(TestCase):
    def test_zero_and_unknown_sampling_are_distinct(self):
        world=deepcopy(source("mixed"))
        for h in world["population_histories"]:h["final_population"]=0.0
        result=demographic_fragment(world)
        self.assertTrue(all(r["population"]==0.0 for r in result["household_cohorts"]))
        self.assertEqual(result["individual_agents"],[]);self.assertEqual(result["individual_life_events"],[])
        self.assertTrue(result["summary"]["individual_sampling_complete"])
        self.assertEqual(result["summary"]["total_property_transfer_value_index"],0.0)
        self.assertTrue(all(r["individual_sampling_status"]=="known_zero_population" for r in result["population_annotations"].values()))
        unknown=demographic_fragment(source("mixed"))
        self.assertFalse(unknown["summary"]["individual_sampling_complete"])
        self.assertIsNone(unknown["summary"]["total_property_transfer_value_index"])

    def test_known_positive_firm_and_people_with_unknown_dependencies(self):
        world=deepcopy(source())
        for p in world["population_regions"]:p["population_pressure"]=None
        for e in world["economy_histories"]:e["steps"][-1]["trade_output_index"]=None
        result=demographic_fragment(world)
        self.assertEqual(len(result["firm_agents"]),8)
        self.assertEqual(len(result["individual_agents"]),12)
        self.assertTrue(any(p["birth_year_bp"] is not None and p["death_year_bp"] is None for p in result["individual_agents"]))
        self.assertTrue(any(p["role"] is None and p["role_available"] is False for p in result["individual_agents"]))
        self.assertIsNone(result["summary"]["total_firm_employment_capacity"])
        self.assertTrue(all(r["firm_candidate_sector_coverage"][2]["selected"] is None for r in result["political_annotations"].values()))

    def test_supported_positive_partial_firm_attributes(self):
        world=deepcopy(source());world["logistics_networks"][0]["logistics_resilience_index"]=None
        result=demographic_fragment(world)
        first=[f for f in result["firm_agents"] if f["region_id"]==world["logistics_networks"][0]["region_id"]]
        self.assertEqual(len(first),5)
        self.assertTrue(all(f["output_index"]>0 and f["employment_capacity"] is None for f in first))
        self.assertTrue(result["political_annotations"][first[0]["region_id"]]["firm_selection_complete"])

    def test_complete_empty_numeric_scope(self):
        world=deepcopy(source())
        for key in ("population_regions","population_histories","economy_histories","political_regions","settlements","logistics_networks","market_exchanges","routes","historical_eras"):world[key]=[]
        result=demographic_fragment(world)
        self.assertTrue(all(result[k]==[] for k in da.COLLECTIONS))
        self.assertTrue(result["summary"]["firm_selection_complete"])
        self.assertTrue(result["summary"]["individual_sampling_complete"])
        world.update({k:result[k] for k in da.COLLECTIONS});world["summary"].update(result["summary"])
        result=market_fragment(world)
        self.assertTrue(all(result[k]==[] for k in ma.FIELD_SCHEMAS))
        self.assertTrue(result["summary"]["market_order_selection_complete"])
        self.assertEqual(result["summary"]["total_market_cleared_volume_index"],0.0)

    def test_market_state_zero_unknown_and_known_physical_slots(self):
        for tax,available in ((0.0,True),(None,False)):
            world=deepcopy(demographic_world())
            for exchange in world["market_exchanges"]:exchange["tax_revenue_index"]=tax
            result=market_fragment(world)
            self.assertFalse(any(o["agent_type"]=="state" for o in result["market_agent_orders"]))
            for row in result["market_clearing_records"]:
                self.assertEqual(row["order_family_availability"]["state"],available)
                self.assertEqual(row["endogenous_demand_index"] is not None,available)
                self.assertIsNotNone(row["requested_volume_index"])
            self.assertEqual(len(result["market_price_iterations"]),30)

    def test_market_firm_first_three_and_fallback_completeness(self):
        world=deepcopy(demographic_world());exchange=world["market_exchanges"][0];origin=exchange["region_from"];target=exchange["region_to"]
        grouped=m._firms_by_region(world)
        selected,available=m._selected_source_firms(world,origin,target,grouped)
        self.assertEqual(selected,grouped[origin][:3]);self.assertTrue(available)
        for r in world["political_regions"]:
            if r["id"]==target:r["firm_selection_complete"]=False
        self.assertTrue(m._selected_source_firms(world,origin,target,grouped)[1])
        world["firm_agents"]=[f for f in world["firm_agents"] if f["region_id"]!=origin]
        self.assertEqual(m._selected_source_firms(world,origin,target,m._firms_by_region(world)),([],False))
        result=market_fragment(world)
        row=next(r for r in result["market_clearing_records"] if r["market_exchange_id"]==exchange["id"])
        self.assertIsNone(row["endogenous_supply_index"])
        self.assertFalse(row["order_family_availability"]["firm"])
        self.assertFalse(result["summary"]["market_order_selection_complete"])
