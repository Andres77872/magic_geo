"""Native-stage retained inputs and scoped scalar history/economy availability.

The environment units are actual native stage outputs with prescribed synthetic
annual context. They are not full climate certificates. Fragment tests call the
owned equation bodies directly and never claim whole-parent/public acceptance.
"""
from copy import deepcopy
from functools import lru_cache
from unittest import TestCase
from unittest.mock import patch
import math

from magic_geo import history_dynamics as population
from magic_geo import economy_dynamics as economy
from magic_geo import history_economy_validation as audit
from support.native_social_worlds import annotated_environment_social_world
from support.legacy_human_water_worlds import legacy_human_water_world


@lru_cache(None)
def source(name="healthy"):
    return annotated_environment_social_world(name)


@lru_cache(None)
def completed(name="healthy"):
    world=deepcopy(source(name))
    population.enrich_world_with_population_history(world)
    economy.enrich_world_with_economy_history(world)
    assert audit.validate_history_economy_replay(world)==[]
    return world


def changed(value):
    if type(value) is bool:return not value
    if value is None:return 0.0
    if type(value) in (int,float):return value+1
    if type(value) is str:return value+"_wrong"
    if type(value) is list:return value[:-1] if value else ["extra"]
    if type(value) is dict:return {**value,"extra":True}
    raise AssertionError(value)


def strip_maps(value):
    if type(value) is dict:return {k:strip_maps(v) for k,v in value.items() if k!="estimate_availability"}
    if type(value) is list:return [strip_maps(v) for v in value]
    return value


class RetainedHistoryEconomyAvailability(TestCase):
    def test_actual_healthy_replay_and_old_numeric_parity(self):
        new=completed(); old=deepcopy(source())
        population._enrich_population_history_v1(old)
        economy._enrich_economy_history_v1(old)
        for stage in ("population","economy"):
            self.assertEqual(strip_maps(new[stage+"_histories"]),old[stage+"_histories"])
            for key in audit.history_summary_fields(stage):
                if key in old["summary"] and key!=stage+"_history_model":self.assertEqual(new["summary"][key],old["summary"][key])
        self.assertEqual(new["summary"]["population_history_available_step_count"],8)
        self.assertEqual(new["summary"]["economy_history_available_step_count"],8)

    def test_actual_mixed_preserves_grid_and_nulls(self):
        world=completed("mixed")
        for stage in ("population","economy"):
            rows=world[stage+"_histories"]
            self.assertEqual(len(rows),2)
            self.assertEqual([[s["era_id"] for s in r["steps"]] for r in rows],[[0,1,2,3]]*2)
            self.assertEqual(world["summary"][stage+"_history_available_step_count"],0)
            for r in rows:
                for obj in [r,*r["steps"]]:
                    for key,flag in obj["estimate_availability"].items():
                        self.assertIs(type(flag),bool)
                        self.assertEqual(obj[key] is not None,flag)
        self.assertIsNone(world["summary"]["historical_final_population"])
        self.assertIsNone(world["summary"]["historical_final_treasury_index"])
        self.assertTrue(any(s["hazard_mortality_index"] is not None for h in world["population_histories"] for s in h["steps"]))

    def test_old_complete_archive_exact_public_parity(self):
        world=legacy_human_water_world("small_smoke")
        self.assertEqual(audit.validate_history_economy_replay(world),[])
        before=deepcopy(world)
        population.enrich_world_with_population_history(world)
        economy.enrich_world_with_economy_history(world)
        self.assertEqual(world,before)
        self.assertEqual(audit.validate_history_economy_replay(world),[])

    def test_idempotence_and_all_unowned_sources_unchanged(self):
        for name in ("healthy","mixed"):
            with self.subTest(name=name):
                world=deepcopy(source(name));before=deepcopy(world)
                population.enrich_world_with_population_history(world);economy.enrich_world_with_economy_history(world)
                for key,value in before.items():
                    if key!="summary":self.assertEqual(world[key],value)
                for key,value in before["summary"].items():self.assertEqual(world["summary"][key],value)
                result=deepcopy(world)
                population.enrich_world_with_population_history(world);economy.enrich_world_with_economy_history(world)
                self.assertEqual(world,result)

    def test_every_record_and_step_field_is_replayed(self):
        base=completed()
        for stage in ("population","economy"):
            for step in (False,True):
                template=base[stage+"_histories"][0]
                if step:template=template["steps"][0]
                for key in template:
                    for operation in ("change","delete"):
                        with self.subTest(stage=stage,step=step,key=key,operation=operation):
                            world=deepcopy(base);row=world[stage+"_histories"][0]
                            if step:row=row["steps"][0]
                            if operation=="delete":del row[key]
                            else:row[key]=changed(row[key])
                            self.assertTrue(audit.validate_history_economy_replay(world))

    def test_every_summary_and_own_model_field_replayed(self):
        for stage in ("population","economy"):
            for kind,keys in (("summary",audit.history_summary_fields(stage)),(stage+"_history_model",completed()[stage+"_history_model"])):
                for key in keys:
                    with self.subTest(stage=stage,kind=kind,key=key):
                        world=deepcopy(completed());world[kind][key]=changed(world[kind][key])
                        self.assertTrue(audit.validate_history_economy_replay(world))

    def test_typed_nullable_flags_no_zero_substitution(self):
        for name in ("healthy","mixed"):
            for stage in ("population","economy"):
                for step in (False,True):
                    template=completed(name)[stage+"_histories"][0]
                    if step:template=template["steps"][0]
                    for key in template["estimate_availability"]:
                        with self.subTest(name=name,stage=stage,step=step,key=key):
                            world=deepcopy(completed(name));row=world[stage+"_histories"][0]
                            if step:row=row["steps"][0]
                            row["estimate_availability"][key]=int(row["estimate_availability"][key])
                            self.assertTrue(audit.validate_history_economy_replay(world))
                    world=deepcopy(completed(name));row=world[stage+"_histories"][0]
                    if step:row=row["steps"][0]
                    key=next(iter(row["estimate_availability"]));row[key]=False
                    self.assertTrue(audit.validate_history_economy_replay(world))

    def test_output_shapes_nonfinite_and_extra_fields_fail_closed(self):
        mutations=[lambda w:w["population_histories"].__setitem__(0,None),
            lambda w:w["economy_histories"][0].__setitem__("steps",None),
            lambda w:w["population_histories"][0]["steps"].__setitem__(0,1),
            lambda w:w["economy_histories"][0]["steps"][0].__setitem__("population",math.nan),
            lambda w:w["economy_histories"][0]["steps"][0].__setitem__("population",math.inf),
            lambda w:w["economy_histories"][0].__setitem__("time_step_count",4.0),
            lambda w:w["population_histories"][0].__setitem__("unexpected",0),
            lambda w:w["economy_histories"].append(deepcopy(w["economy_histories"][0]))]
        for i,mutate in enumerate(mutations):
            with self.subTest(case=i):
                world=deepcopy(completed());mutate(world)
                self.assertTrue(audit.validate_history_economy_replay(world))
        for malformed in (None,[],False,{}, {"summary":[]}):self.assertTrue(audit.validate_history_economy_replay(malformed))

    def test_own_dispatch_precedes_bad_parent_and_partial_mirrors(self):
        for stage,producer in (("population",population.enrich_world_with_population_history),("economy",economy.enrich_world_with_economy_history)):
            world=deepcopy(completed());world[stage+"_history_model"]["deterministic"]=1;world["native_social_availability"]=None
            before=deepcopy(world)
            with self.assertRaisesRegex(ValueError,"unknown or malformed own"):producer(world)
            self.assertEqual(world,before)
            for key in [stage+"_histories",*audit.history_summary_fields(stage)]:
                world=deepcopy(source());
                if key==stage+"_histories":world[key]=[]
                else:world["summary"][key]=0
                before=deepcopy(world)
                with self.assertRaises(ValueError):producer(world)
                self.assertEqual(world,before)
            world=deepcopy(completed());world[stage+"_history_model"]=(audit._population_model() if stage=="population" else audit._economy_model())
            world["summary"][stage+"_history_model"]=world[stage+"_history_model"]["model_type"]
            before=deepcopy(world)
            with self.assertRaisesRegex(ValueError,"exact native family"):producer(world)
            self.assertEqual(world,before)

    def test_legacy_economy_rejects_declared_successor_population_parent(self):
        world=legacy_human_water_world("small_smoke")
        world["population_history_model"]=population._population_history_model_v2()
        world["summary"]["population_history_model"]=population.POPULATION_HISTORY_V2
        before=deepcopy(world)
        with self.assertRaisesRegex(ValueError,"exact population-history parent"):
            economy.enrich_world_with_economy_history(world)
        self.assertEqual(world,before)

    def test_missing_changed_native_sources_atomic_first_and_reenrichment(self):
        mutations=[lambda w:w.pop("territorial_snapshots"),lambda w:w["territorial_snapshots"][0]["regions"].pop(),
            lambda w:w["territorial_snapshots"][0]["regions"][0].__setitem__("estimated_population",1.),
            lambda w:w["population_regions"][0].pop("migration_balance"),
            lambda w:w["population_regions"][0].__setitem__("growth_rate_per_year",False),
            lambda w:w["historical_eras"][0].__setitem__("mean_instability_available",1),
            lambda w:w.pop("conflicts"),lambda w:w["native_social_availability"].__setitem__("conflict_inference_available",False)]
        for enriched in (False,True):
            for i,mutate in enumerate(mutations):
                with self.subTest(enriched=enriched,case=i):
                    world=deepcopy(completed() if enriched else source());mutate(world);before=deepcopy(world)
                    with self.assertRaises((ValueError,KeyError,TypeError)):population.enrich_world_with_population_history(world)
                    self.assertEqual(world,before)

    def test_economy_exact_population_and_trade_parents_atomic(self):
        mutations=[lambda w:w.pop("population_history_model"),lambda w:w["population_histories"][0]["steps"][0].__setitem__("end_population",0.),
            lambda w:w.pop("trade_flows"),lambda w:w["trade_flows"][0].__setitem__("volume_index",False),
            lambda w:w["political_regions"][0].pop("dominant_resource"),
            lambda w:w["trade_flow_model"].__setitem__("deterministic",1)]
        for i,mutate in enumerate(mutations):
            with self.subTest(case=i):
                world=deepcopy(completed());mutate(world);before=deepcopy(world)
                with self.assertRaises((ValueError,KeyError,TypeError)):economy.enrich_world_with_economy_history(world)
                self.assertEqual(world,before)

    def test_poisoned_producer_arithmetic_rejected_before_commit(self):
        for enriched in (False,True):
            world=deepcopy(completed() if enriched else source());before=deepcopy(world)
            original=population._build_population_history_v2
            def bad(*args):
                records,summary=original(*args);records[0]["steps"][0]["migration_delta"]+=.001;return records,summary
            with patch.object(population,"_build_population_history_v2",bad):
                with self.assertRaises(ValueError):population.enrich_world_with_population_history(world)
            self.assertEqual(world,before)
            world=deepcopy(completed());
            if not enriched:
                world.pop("economy_history_model");world.pop("economy_histories")
                for key in audit.history_summary_fields("economy"):world["summary"].pop(key,None)
            before=deepcopy(world)
            with patch.object(economy,"_resource_value",return_value=.99):
                with self.assertRaises(ValueError):economy.enrich_world_with_economy_history(world)
            self.assertEqual(world,before)


class ScopedHistoryEquationControls(TestCase):
    """Explicit mathematical fragments, not malformed public parent fixtures."""
    def population_pair(self,world):
        envelope={"conflict_inference_available":True}
        actual=population._build_population_history_v2(world,envelope)
        expected=audit._expected_population_v2(world,envelope)
        self.assertEqual(actual,expected)
        return actual

    def test_known_zero_capacity_population_and_empty_scope(self):
        world=deepcopy(source());world["conflicts"]=[]
        for p in world["population_regions"]:
            p["carrying_capacity"]=0.;p["estimated_population"]=0.;p["population_pressure"]=0.
        for snapshot in world["territorial_snapshots"]:
            for region in snapshot["regions"]:region["estimated_population"]=0.
        histories,summary=self.population_pair(world)
        self.assertEqual(summary["historical_final_population"],0.)
        self.assertTrue(all(h["initial_population"]==h["final_population"]==h["carrying_capacity"]==0. for h in histories))
        self.assertTrue(all(s["pressure_index"]==0. and s["estimate_availability"]["pressure_index"] for h in histories for s in h["steps"]))
        world["population_histories"]=histories
        actual=economy._build_economy_history_v2(world,{"conflict_inference_available":True})
        self.assertEqual(actual,audit._expected_economy_v2(world,histories,{"conflict_inference_available":True}))
        self.assertTrue(all(s["population"]==s["army_capacity_population"]==0. for h in actual[0] for s in h["steps"]))
        empty={"historical_eras":[],"territorial_snapshots":[],"population_regions":[],"conflicts":[],"political_regions":[],"trade_flows":[],"population_histories":[]}
        for producer,replay in ((population._build_population_history_v2,audit._expected_population_v2),):self.assertEqual(producer(empty,{"conflict_inference_available":True}),replay(empty,{"conflict_inference_available":True}))
        self.assertEqual(economy._build_economy_history_v2(empty,{"conflict_inference_available":True}),audit._expected_economy_v2(empty,[],{"conflict_inference_available":True}))

    def test_missing_diagnostics_do_not_replace_actual_snapshot(self):
        world=deepcopy(source());world["conflicts"]=[]
        p=world["population_regions"][0]
        p["growth_rate_per_year"]=None;p["hazard_mortality_index"]=None;p["carrying_capacity"]=None
        histories,_=self.population_pair(world)
        step=histories[0]["steps"][0]
        self.assertIsNotNone(step["end_population"])
        self.assertIsNone(step["growth_rate_per_year"]);self.assertIsNone(step["pressure_index"])
        world["territorial_snapshots"][0]["regions"][0]["estimated_population"]=None
        histories,_=self.population_pair(world)
        self.assertIsNone(histories[0]["initial_population"])
        self.assertIsNone(histories[0]["steps"][0]["end_population"])
        self.assertIsNone(histories[0]["steps"][1]["start_population"])
        self.assertIsNotNone(histories[0]["steps"][1]["end_population"])
        self.assertIsNone(histories[0]["peak_population"])

    def test_economy_retains_independent_diagnostics_and_unknown_cash(self):
        world=deepcopy(completed())
        world["population_histories"][0]["initial_population"]=None
        for s in world["population_histories"][0]["steps"]:s["end_population"]=None
        env={"conflict_inference_available":True}
        actual=economy._build_economy_history_v2(world,env)
        self.assertEqual(actual,audit._expected_economy_v2(world,world["population_histories"],env))
        for step in actual[0][0]["steps"]:
            for key in ("trade_output_index","trade_revenue_index","mobilized_force_population","war_cost_index","stability_index"):self.assertIsNotNone(step[key])
            for key in ("population","gross_output_index","treasury_start_index","treasury_end_index"):self.assertIsNone(step[key])
        self.assertIsNone(actual[1]["historical_final_gross_output_index"])
        self.assertIsNotNone(actual[1]["historical_total_trade_revenue_index"])
        self.assertIsNotNone(actual[1]["historical_total_war_cost_index"])

    def test_exact_era_lookup_ignores_positional_permutation(self):
        world=deepcopy(completed());env={"conflict_inference_available":True}
        expected=economy._build_economy_history_v2(world,env)
        world["historical_eras"].reverse()
        self.assertEqual(economy._build_economy_history_v2(world,env),expected)
        self.assertEqual(audit._expected_economy_v2(world,world["population_histories"],env),expected)

    def test_positive_population_zero_capacity_pressure_unavailable(self):
        world=deepcopy(source());world["population_regions"][0]["carrying_capacity"]=0.
        histories,summary=self.population_pair(world)
        self.assertGreater(histories[0]["final_population"],0.)
        self.assertIsNone(histories[0]["peak_pressure_index"])
        self.assertIsNone(summary["historical_peak_population_pressure"])

    def test_raw_rounding_sequence_and_conflict_cap(self):
        world=deepcopy(source());p=world["population_regions"][0];p["migration_balance"]=.123456789
        world["conflicts"]=[{"era_id":0,"region_a":0,"region_b":-1,"estimated_casualties":1.e9}]
        histories,_=self.population_pair(world)
        first=histories[0]["steps"][0];snapshot=world["territorial_snapshots"][0]["regions"][0]["estimated_population"]
        self.assertEqual(first["conflict_loss"],round(snapshot*.35,6))
        raw=snapshot+snapshot*.123456789*.035*(1800./1000.)-snapshot*.35
        self.assertEqual(first["end_population"],round(raw,6))
        self.assertEqual(histories[0]["steps"][1]["start_population"],round(raw,6))

    def test_overflow_never_publishes_a_finite_masked_result(self):
        with self.assertRaises(ValueError):population._history_complete([1e308,1e308])
        with self.assertRaises(ValueError):economy._economic_aggregate([1e308,1e308])
        with self.assertRaises(ValueError):audit._aggregate([1e308,1e308])
