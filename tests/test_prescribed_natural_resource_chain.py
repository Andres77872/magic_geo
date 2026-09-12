"""Focused exact-version resource migration; retained/stage inputs, no generation."""
from copy import deepcopy
import math

import pytest

from magic_geo import resource_dynamics as resources, commodity_resources as commodities, worldbuilding_realism as worldbuilding
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS, validate_aquatic_climate_support
from magic_geo.biological_resource_validation import (
    BiologicalResourceValidationError, biological_resource_contract,
    validate_biological_resources, _DEPOSIT_V2,
)
from magic_geo.ecosystem_dynamics import enrich_world_with_ecosystem_dynamics
from magic_geo.worldbuilding_fishery_validation import (
    WorldbuildingFisheryValidationError, validate_worldbuilding_fishery_context, _V1,
)
from support.prescribed_resource_worlds import (
    OWNERS, retained_resource_world, fresh_resource_inputs,
    clear_resource_stage, owned_resource_stage,
)


PRODUCERS={"resource":resources.enrich_world_with_resource_deposits,
           "commodity":commodities.enrich_world_with_commodity_occurrences,
           "worldbuilding":worldbuilding.enrich_world_with_worldbuilding_realism}
NATIVE=("climate_model","climate_energy_model","climate_energy_balance_records",
        "climate_energy_forcing_intervals","climate_energy_transport_edges")


def chain(world, *, human=True):
    PRODUCERS["resource"](world)
    PRODUCERS["commodity"](world)
    if human:PRODUCERS["worldbuilding"](world)
    return world


def ready(stage,scope="full"):
    world=fresh_resource_inputs(scope)
    if stage in ("commodity","worldbuilding"):PRODUCERS["resource"](world)
    if stage=="worldbuilding":PRODUCERS["commodity"](world)
    return world


def assert_atomic(world,stage,match=None):
    before=deepcopy(world)
    refs={k:v for k,v in world.items() if isinstance(v,(list,dict))}
    cells=list(world["cells"])
    with pytest.raises((BiologicalResourceValidationError,WorldbuildingFisheryValidationError),match=match):
        PRODUCERS[stage](world)
    assert world==before
    assert all(world[k] is v for k,v in refs.items())
    assert all(c is d for c,d in zip(cells,world["cells"]))


@pytest.mark.parametrize("scope",["full","geo"])
def test_actual128_chain_preserves_material_resource_access_and_native_objects(scope):
    old=retained_resource_world(scope);world=fresh_resource_inputs(scope)
    refs={k:world[k] for k in NATIVE}
    cells=world["cells"];summary=world["summary"];physical=[dict(c) for c in cells]
    chain(world,human=scope=="full")
    assert validate_biological_resources(world)==[]
    assert world["resource_deposit_model"]["model_type"].endswith("_v4")
    assert world["commodity_occurrence_model"]["model_type"].endswith("_v2")
    # Every material/reserve/confidence/renewability/access/evidence value and
    # dense link is unchanged for these SAME inputs. Full/geo access need not match.
    assert world["resource_deposits"]==old["resource_deposits"]
    assert world["commodity_occurrences"]==old["commodity_occurrences"]
    # This actual current witness includes freshwater fisheries; the unchanged
    # marine navigation mask is not reused as a fishery habitat selector.
    lakes={c["id"] for c in cells if c["water_body_type"]=="fresh_lake" and c["resource"]=="coastal_fisheries"}
    assert len(lakes)==3
    assert lakes <= {r["cell_id"] for r in world["commodity_occurrences"] if r["commodity"]=="fishery_biomass"}
    for stage in ("resource","commodity"):
        assert owned_resource_stage(world,stage)["summary"]==owned_resource_stage(old,stage)["summary"]
    for before,after in zip(physical,cells):
        assert all(after[k]==v for k,v in before.items())
    assert world["cells"] is cells and world["summary"] is summary
    assert all(world[k] is v for k,v in refs.items())
    if scope=="full":
        assert world["worldbuilding_realism_checks"]==old["worldbuilding_realism_checks"]
        assert validate_worldbuilding_fishery_context(world)==[]
        assert world["worldbuilding_realism_model"]["model_type"].endswith("_v3")
    else:
        assert "worldbuilding_realism_model" not in world
        assert "settlements" not in world
    before=deepcopy(world);chain(world,human=scope=="full")
    assert world==before and world["cells"] is cells and world["summary"] is summary
    assert all(world[k] is v for k,v in refs.items())


@pytest.mark.parametrize("scope",["full","geo"])
def test_exact_historical_e4_chain_retains_whole_output(scope):
    world=retained_resource_world(scope);before=deepcopy(world)
    chain(world,human=scope=="full")
    assert world==before


def test_established_deposit2_e4_promotion_is_retained():
    world=retained_resource_world()
    clear_resource_stage(world,"commodity")
    clear_resource_stage(world,"resource")
    resources._enrich_world_with_resource_deposits_legacy(world)
    assert world["resource_deposit_model"]["model_type"]==_DEPOSIT_V2["model_type"]
    resources.enrich_world_with_resource_deposits(world)
    assert world["resource_deposit_model"]["model_type"].endswith("_v3")
    assert validate_biological_resources(world,include_commodities=False)==[]


def test_exact_worldbuilding1_retains_declared_exception_with_new_resource_chain():
    world=chain(fresh_resource_inputs(),human=False)
    world["worldbuilding_realism_model"]=deepcopy(_V1)
    world["summary"]["worldbuilding_realism_model"]=_V1["model_type"]
    worldbuilding.enrich_world_with_worldbuilding_realism(world)
    assert world["worldbuilding_realism_model"]==_V1
    assert validate_worldbuilding_fishery_context(world)==[]


@pytest.mark.parametrize("stage",PRODUCERS)
@pytest.mark.parametrize("value",[None,{},"model",{"model_type":"unknown"}])
def test_malformed_own_declaration_rejects_atomically_before_publication(stage,value):
    world=ready(stage)
    world[OWNERS[stage][2][1 if stage!="worldbuilding" else 0]]=value
    assert_atomic(world,stage)


@pytest.mark.parametrize("stage",PRODUCERS)
def test_known_old_own_identity_cannot_be_retagged_against_e5(stage):
    world=ready(stage);old=retained_resource_world()
    model_key="worldbuilding_realism_model" if stage=="worldbuilding" else OWNERS[stage][2][1]
    world[model_key]=deepcopy(old[model_key])
    if stage=="worldbuilding":world["summary"][model_key]=old["summary"][model_key]
    assert_atomic(world,stage,"parent")


@pytest.mark.parametrize("stage",PRODUCERS)
def test_new_own_identity_rejects_historical_parent(stage):
    world=chain(fresh_resource_inputs());world["ecosystem_dynamics_model"]=deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])
    assert_atomic(world,stage,"parent")


@pytest.mark.parametrize("stage",PRODUCERS)
@pytest.mark.parametrize("published",[False,True])
def test_missing_ecosystem_declaration_never_falls_back_with_retained_parent_outputs(stage,published):
    world=ready(stage)
    if published:PRODUCERS[stage](world)
    del world["ecosystem_dynamics_model"]
    assert_atomic(world,stage,"parent")


@pytest.mark.parametrize("stage",PRODUCERS)
@pytest.mark.parametrize("kind",["cell","summary","record"])
def test_missing_new_own_identity_with_any_owned_mirror_rejects(stage,kind):
    if stage=="worldbuilding" and kind=="cell":pytest.skip("worldbuilding owns no cell fields")
    world=ready(stage)
    fields,summaries,tops=OWNERS[stage]
    if kind=="cell":world["cells"][-1][fields[-1]]=False
    elif kind=="summary":world["summary"][summaries[-1]]=0
    else:world[next(k for k in tops if not k.endswith("model"))]=[]
    assert_atomic(world,stage,"undeclared|identity")


RESOURCE_INPUTS=("resource","flow_accumulation","boundary_convergent","boundary_divergent","boundary_transform",
    "sediment_thickness_m","crust_age_ma","soil_salinity_index","elevation_m","area_km2","lat_deg","lon_deg",
    "landform","crust_type","lithology","boundary_type","is_river","basin_id")


@pytest.mark.parametrize("published",[False,True])
@pytest.mark.parametrize("key",RESOURCE_INPUTS)
def test_actual_emitted_resource_missing_source_is_not_defaulted(key,published):
    world=ready("resource")
    if published:resources.enrich_world_with_resource_deposits(world)
    cell=next(c for c in reversed(world["cells"]) if c["resource"] not in ("none","coastal_fisheries"))
    assert key in cell
    del cell[key]
    assert_atomic(world,"resource",key)
    if published:assert validate_biological_resources(world,include_commodities=False)


@pytest.mark.parametrize("key",["resource","flow_accumulation"])
def test_all_cell_normalization_and_resource_classification_require_explicit_inputs(key):
    world=ready("resource");cell=next(c for c in world["cells"] if c["resource"]=="none")
    del cell[key]
    assert_atomic(world,"resource",key)


@pytest.mark.parametrize("value",[None,"0.5",True,math.inf,math.nan])
def test_retained_access_rejects_malformed_score_only_where_consumed(value):
    world=ready("resource");cell=next(c for c in world["cells"] if c["resource"]!="none")
    cell["settlement_score"]=value
    # NaN is retained by deepcopy by identity but equality of the whole object is
    # still safe for this unchanged container; no NaN value is synthesized.
    assert_atomic(world,"resource","settlement_score")


def test_missing_score_and_optional_human_links_keep_historical_geo_defaults():
    world=ready("resource","geo")
    assert all("settlement_score" not in c for c in world["cells"])
    chain(world,human=False)
    assert validate_biological_resources(world)==[]
    assert all(r["political_region_id"]==r["culture_region_id"]==-1 for r in world["resource_deposits"])


def test_unconsumed_missing_material_fields_and_poison_score_do_not_become_global_requirements():
    world=ready("resource");cell=next(c for c in world["cells"] if c["resource"]=="none")
    for key in ("lithology","boundary_type","basin_id"):cell.pop(key)
    cell["settlement_score"]=None
    resources.enrich_world_with_resource_deposits(world)
    assert validate_biological_resources(world,include_commodities=False)==[]


@pytest.mark.parametrize("key",["sedimentary_resource_systems","volcanic_potential_index"])
@pytest.mark.parametrize("published",[False,True])
def test_commodity_missing_consumed_material_source_rejects_atomically(key,published):
    world=ready("commodity")
    if published:commodities.enrich_world_with_commodity_occurrences(world)
    if key=="sedimentary_resource_systems":del world[key]
    else:del world["cells"][world["resource_deposits"][-1]["cell_id"]][key]
    assert_atomic(world,"commodity",key)


@pytest.mark.parametrize("key",["id","basin_id","system_confidence_index","petroleum_potential_index","gas_potential_index","coal_potential_index","evaporite_salt_potential_index"])
def test_consumed_sedimentary_system_fields_cannot_disappear(key):
    world=ready("commodity");record=next(r for r in world["sedimentary_resource_systems"] if r["basin_id"]>=0)
    assert key in record;del record[key]
    assert_atomic(world,"commodity",key)


@pytest.mark.parametrize("key",["settlements","routes","political_regions","borders","neighbors"])
@pytest.mark.parametrize("published",[False,True])
def test_worldbuilding_missing_preceding_source_rejects_atomically(key,published):
    world=ready("worldbuilding")
    if published:worldbuilding.enrich_world_with_worldbuilding_realism(world)
    if key=="neighbors":del world["cells"][-1][key]
    else:del world[key]
    assert_atomic(world,"worldbuilding","neighbor" if key=="neighbors" else key)


def test_explicit_empty_human_collections_are_valid_with_nonempty_cells():
    world=ready("worldbuilding")
    for key in ("settlements","routes","political_regions","borders"):world[key]=[]
    worldbuilding.enrich_world_with_worldbuilding_realism(world)
    assert validate_worldbuilding_fishery_context(world)==[]
    assert all(c["value"]==1.0 for c in world["worldbuilding_realism_checks"][:4])


def test_empty_resource_outputs_are_valid_but_empty_worldbuilding_scope_rejects():
    world={"cells":[],"summary":{},"sedimentary_resource_systems":[],"settlements":[],"routes":[],"political_regions":[],"borders":[]}
    enrich_world_with_ecosystem_dynamics(world)
    chain(world,human=False)
    assert validate_biological_resources(world)==[]
    assert world["resource_deposits"]==world["commodity_occurrences"]==[]
    assert_atomic(world,"worldbuilding","nonempty")


@pytest.mark.parametrize("temperature",[-100.0,-18.0,44.0,100.0])
def test_unavailable_fishery_in_complete_scoped_e5_stage_inputs_retains_native_label(temperature):
    # Extracted actual physical fields, with a controlled annual-air input. This
    # is a stage experiment, not a modified native climate certificate/world.
    original=retained_resource_world()
    source=deepcopy(next(c for c in original["cells"] if c["resource"]=="coastal_fisheries"))
    source.update(id=0,temperature_c=temperature,neighbors=[])
    world={"cells":[source],"summary":{},"sedimentary_resource_systems":[]}
    for stage in OWNERS:clear_resource_stage(world,stage)
    enrich_world_with_ecosystem_dynamics(world)
    chain(world,human=False)
    assert world["cells"][0]["resource"]=="coastal_fisheries"
    assert world["cells"][0]["fishery_resource_proxy_applicable"] is True
    assert world["cells"][0]["fishery_resource_proxy_supported"] is False
    assert world["resource_deposits"]==world["commodity_occurrences"]==[]
    assert validate_biological_resources(world)==[]


def test_supported_zero_inputs_keep_established_explicit_e4_consumer_contract():
    source=deepcopy(next(c for c in retained_resource_world()["cells"] if c["resource"]=="coastal_fisheries"))
    source.update(id=0,temperature_c=18.0,neighbors=[])
    world={"cells":[source],"summary":{},"sedimentary_resource_systems":[]}
    for stage in OWNERS:clear_resource_stage(world,stage)
    world["ecosystem_dynamics_model"]=deepcopy(_EXPECTED_MODELS["heuristic_ecosystem_climate_support_v4"])
    enrich_world_with_ecosystem_dynamics(world)
    source.update(primary_productivity_index=0.0,fishery_productivity_index=0.0)
    world["renewable_resource_records"]=[]
    assert validate_aquatic_climate_support(world)==[]
    chain(world,human=False)
    assert source["fishery_resource_proxy_supported"] is source["fishery_commodity_supported"] is True
    assert len(world["resource_deposits"])==len(world["commodity_occurrences"])==1
    assert validate_biological_resources(world)==[]


@pytest.mark.parametrize("stage",["resource","commodity"])
def test_tampered_supported_parent_record_cannot_feed_consumer(stage):
    world=chain(fresh_resource_inputs(),human=False)
    if stage=="resource":
        world["cells"][-1]["ecosystem_disturbance_pressure_index"]+=.01
        consumer="resource"
    else:
        world["resource_deposits"].pop();consumer="commodity"
    assert_atomic(world,consumer)


@pytest.mark.parametrize("stage",PRODUCERS)
def test_wrong_producer_equation_is_rejected_before_owned_commit(stage,monkeypatch):
    world=ready(stage)
    if stage=="resource":monkeypatch.setattr(resources,"_reserve_potential",lambda *a,**k:.999999)
    elif stage=="commodity":monkeypatch.setattr(commodities,"_commodity_potential",lambda *a,**k:.999999)
    else:monkeypatch.setattr(worldbuilding,"_settlement_has_water",lambda *a,**k:False)
    assert_atomic(world,stage)


@pytest.mark.parametrize("stage",PRODUCERS)
def test_output_support_record_and_summary_tampering_is_independently_rejected(stage):
    world=chain(fresh_resource_inputs())
    if stage=="resource":
        r=next(r for r in world["resource_deposits"] if r["resource"]=="coastal_fisheries")
        r["reserve_potential_index"]+=.01
        assert validate_biological_resources(world,include_commodities=False)
    elif stage=="commodity":
        r=next(r for r in world["commodity_occurrences"] if r["commodity"]=="fishery_biomass")
        r["occurrence_potential_index"]+=.01
        assert validate_biological_resources(world)
    else:
        world["worldbuilding_realism_checks"][4]["evidence"]["source_context_supported_resource_deposit_count"]-=1
        assert validate_worldbuilding_fishery_context(world)
