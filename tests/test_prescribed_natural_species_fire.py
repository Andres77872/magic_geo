"""Matched E5 children, real retained inputs and isolated descriptor/graph controls."""
from copy import deepcopy
import math,pickle,json
import pytest
from magic_geo import ecosystem_dynamics as eco
from magic_geo import species_ranges as species
from magic_geo import wildfire_disturbance as fire
from magic_geo.species_habitat_validation import validate_species_habitat_support as species_audit, _EXPECTED_V4_MODEL
from magic_geo.wildfire_aquatic_validation import validate_wildfire_aquatic_exclusion as fire_audit, _NATURAL_FIRE_MODELS
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS
from support.prescribed_activity_worlds import *

SPECIES_EXTRA_NUMERIC=('reef_growth_index','wetland_extent_index','biome_confidence_index','wetland_hydrology_index','river_channel_width_m','river_channel_depth_m','elevation_m','permafrost_extent_index','distance_to_marine_water_km','area_km2','lat_deg','lon_deg')
SPECIES_EXTRA_TYPED=('is_river','biome_ecotone_type','island_class','reef_type','wetland_system_type','wetland_system_id','reef_system_id','aquifer_system_id','basin_id')
FIRE_EXTRA=('wetland_extent_index','floodplain_connectivity_index','lat_deg','lon_deg','elevation_m','area_km2','is_river')

@pytest.fixture(scope='module')
def current():return {s:build_activity_world(fresh_activity_world(s)) for s in ('full','geo')}

def atomic_error(world,producer):
    before=pickle.dumps(world);refs=(world['cells'],world['summary'],*world['cells'])
    with pytest.raises(ValueError) as exc:producer(world)
    assert len(str(exc.value))<=600
    assert pickle.dumps(world)==before
    assert all(a is b for a,b in zip(refs,(world['cells'],world['summary'],*world['cells'])))


def scalar_chain(temperatures=(18.,18.,80.),native=False):
    # Explicit stage-only physical input; this is not a native energy certificate.
    cells=[]
    for i,t in enumerate(temperatures):
        c=dict(id=i,temperature_c=t,neighbors=([i-1] if i else [])+([i+1] if i+1<len(temperatures) else []),area_km2=1.,lat_deg=0.,lon_deg=float(i),is_water=False,is_lake=False,is_river=False,water_body_type='land',biome='temperate_forest',biome_ecotone_type='none',island_class='continent',reef_type='none',wetland_system_type='none',wetland_system_id=-1,reef_system_id=-1,aquifer_system_id=-1,basin_id=-1,
            precipitation_mm_y=1200.,potential_evapotranspiration_mm_y=1000.,soil_moisture_index=1.,fertility=1.,growing_season_months=12.,runoff_mm_y=0.,ocean_current_temperature_c=0.,ocean_current_east=0.,ice_thickness_m=0.,seasonal_aridity_index=1.,soil_organic_matter_fraction=.2,fire_frequency_index=1.,ecotone_index=.4,erosion_rate=0.,wind_east=1.,wind_north=0.,groundwater_recharge_mm_y=0.,wetland_extent_index=0.,floodplain_connectivity_index=0.,climate_energy_stress_index=1.,reef_growth_index=0.,biome_confidence_index=.7,wetland_hydrology_index=0.,river_channel_width_m=0.,river_channel_depth_m=0.,elevation_m=0.,permafrost_extent_index=0.,distance_to_marine_water_km=9999.)
        cells.append(c)
    w={'cells':cells,'summary':{},'wetland_systems':[],'reef_systems':[],'aquifer_systems':[]};eco.enrich_world_with_ecosystem_dynamics(w);return w


def test_actual_full_geo_matched_natural_outputs_are_equal_and_declared(current):
    for stage in ('species','fire'):assert stage_owned(current['full'],stage)==stage_owned(current['geo'],stage)
    for scope,w in current.items():
        assert w['species_ranges_model']==_EXPECTED_V4_MODEL==species.NATURAL_SPECIES_PARENT_MODEL
        assert w['wildfire_disturbance_model']==_NATURAL_FIRE_MODELS[True]==fire.NATIVE_NATURAL_PARENT_WILDFIRE_MODEL
        assert species_audit(w)==fire_audit(w)==[]
        assert w['species_range_records'] and w['wildfire_spread_histories']
        assert all(w[k]==archived_activity_world(scope)[k] for k in NATIVE_KEYS)


@pytest.mark.parametrize('scope',('full','geo'))
def test_actual_historical_species3_fire5_are_exactly_retained(scope):
    w=deepcopy(archived_activity_world(scope));before=json.dumps(w,sort_keys=True)
    species.enrich_world_with_species_ranges(w);fire.enrich_world_with_wildfire_disturbance(w)
    assert json.dumps(w,sort_keys=True)==before
    assert species_audit(w)==fire_audit(w)==[]


@pytest.mark.parametrize('value',[None,True,'unrelated',[],{},math.nan,math.inf,-math.inf,1<<20000,-.5,0.,.4,1.,2.],ids=['null','bool','text','list','dict','nan','inf','-inf','hugeint','negative','zero','interior','one','aboveone'])
def test_new_actual_chain_ignores_all_settlement_score_values(current,value):
    w=fresh_activity_world()
    for c in w['cells']:c['settlement_score']=value
    build_activity_world(w)
    for stage in ('species','fire'):assert stage_owned(w,stage)==stage_owned(current['full'],stage)
    assert all(c['settlement_score'] is value for c in w['cells'])


def test_absent_and_poison_human_and_native_stress_fields_not_read(current):
    class Poison:
        def __float__(self):raise AssertionError('coerced unrelated activity')
        def __bool__(self):raise AssertionError('tested unrelated activity')
        def __str__(self):raise AssertionError('stringified unrelated activity')
    w=build_to_species_inputs(fresh_activity_world());poison=Poison()
    for c in w['cells']:c['settlement_score']=poison;c['climate_energy_stress_index']=poison
    for name in ('settlements','population_histories','routes'):w[name]=poison
    species.enrich_world_with_species_ranges(w);fire.enrich_world_with_wildfire_disturbance(w)
    for stage in ('species','fire'):assert stage_owned(w,stage)==stage_owned(current['full'],stage)
    w=build_to_species_inputs(fresh_activity_world())
    for c in w['cells']:c.pop('settlement_score',None)
    species.enrich_world_with_species_ranges(w);fire.enrich_world_with_wildfire_disturbance(w)
    assert stage_owned(w,'fire')==stage_owned(current['full'],'fire')


@pytest.mark.parametrize('stage',('species','fire'))
@pytest.mark.parametrize('published',(False,True))
def test_publication_preserves_native_source_and_nested_identity(current,stage,published):
    w=deepcopy(current['full']) if published else build_to_species_inputs(fresh_activity_world())
    fn=species.enrich_world_with_species_ranges if stage=='species' else fire.enrich_world_with_wildfire_disturbance
    refs=[w['cells'],w['summary'],w['cells'][0],w['cells'][0]['neighbors'],*[w[k] for k in NATIVE_KEYS]]
    fn(w)
    assert all(a is b for a,b in zip(refs,[w['cells'],w['summary'],w['cells'][0],w['cells'][0]['neighbors'],*[w[k] for k in NATIVE_KEYS]]))
    first=stage_owned(w,stage);fn(w);assert stage_owned(w,stage)==first


@pytest.mark.parametrize('key',SPECIES_EXTRA_NUMERIC+SPECIES_EXTRA_TYPED+('neighbors',))
@pytest.mark.parametrize('published',(False,True))
def test_missing_species_inputs_cannot_default_or_split_components(current,key,published):
    w=deepcopy(current['full']) if published else build_to_species_inputs(fresh_activity_world())
    del w['cells'][-1][key]
    atomic_error(w,species.enrich_world_with_species_ranges)
    if published:assert species_audit(w)


@pytest.mark.parametrize('key',FIRE_EXTRA+('neighbors',))
@pytest.mark.parametrize('published',(False,True))
def test_missing_fire_inputs_cannot_default_or_relabel_unknown(current,key,published):
    w=deepcopy(current['full']) if published else build_to_species_inputs(fresh_activity_world())
    del w['cells'][-1][key]
    atomic_error(w,fire.enrich_world_with_wildfire_disturbance)
    if published:assert fire_audit(w)


@pytest.mark.parametrize('stage',('species','fire'))
@pytest.mark.parametrize('kind',('nonreciprocal','duplicate','self','dangling','bool','string'))
def test_new_complete_graph_contract_is_atomic(current,stage,kind):
    w=deepcopy(current['full']);a=w['cells'][0];j=a['neighbors'][0]
    if kind=='nonreciprocal':w['cells'][j]['neighbors'].remove(a['id'])
    elif kind=='duplicate':a['neighbors'].append(j)
    elif kind=='self':a['neighbors'].append(a['id'])
    elif kind=='dangling':a['neighbors'].append(999999)
    elif kind=='bool':a['neighbors'][0]=True
    else:a['neighbors']='none'
    atomic_error(w,species.enrich_world_with_species_ranges if stage=='species' else fire.enrich_world_with_wildfire_disturbance)


@pytest.mark.parametrize('stage',('species','fire'))
@pytest.mark.parametrize('kind',('old-own-new-parent','new-own-old-parent','null','extra','missing','partial-cell','partial-summary','partial-records'))
def test_exact_dispatch_and_no_partial_own_retagging(current,stage,kind):
    model='species_ranges_model' if stage=='species' else 'wildfire_disturbance_model';records='species_range_records' if stage=='species' else 'wildfire_spread_histories'
    fn=species.enrich_world_with_species_ranges if stage=='species' else fire.enrich_world_with_wildfire_disturbance
    w=deepcopy(current['full'])
    if kind=='old-own-new-parent':w[model]=deepcopy(archived_activity_world()[model])
    elif kind=='new-own-old-parent':w['ecosystem_dynamics_model']=deepcopy(_EXPECTED_MODELS['heuristic_ecosystem_climate_support_v4'])
    elif kind=='null':w[model]=None
    elif kind=='extra':w[model]['extra']=True
    elif kind=='missing':w[model].pop('model')
    else:
        w=build_to_species_inputs(fresh_activity_world())
        if kind=='partial-cell':w['cells'][0][SPECIES_CELLS[0] if stage=='species' else FIRE_CELLS[0]]=False
        elif kind=='partial-summary':w['summary'][SPECIES_SUMMARY[0] if stage=='species' else FIRE_SUMMARY[0]]=0
        else:w[records]=[]
    atomic_error(w,fn)


def test_old_own_metadata_cannot_retag_positive_activity_outputs_as_new(current):
    old=deepcopy(archived_activity_world());new=deepcopy(current['full'])
    # Keep E5 certificate, substitute only historical child results with new labels.
    for c,n in zip(old['cells'],new['cells']):
        for key in FIRE_CELLS:n[key]=deepcopy(c[key])
    for key in FIRE_SUMMARY:new['summary'][key]=deepcopy(old['summary'][key])
    new['wildfire_spread_histories']=deepcopy(old['wildfire_spread_histories'])
    assert fire_audit(new)


@pytest.mark.parametrize('stage',('species','fire'))
def test_independent_oracle_rejects_changed_producer_before_commit(monkeypatch,current,stage):
    w=deepcopy(current['full'])
    if stage=='species':
        original=species._guild_scores
        def wrong(c):
            scores=original(c);scores['canopy_tree']=.99;return scores
        monkeypatch.setattr(species,'_guild_scores',wrong);fn=species.enrich_world_with_species_ranges
    else:
        original=fire._ignition_potential
        def wrong(c,f,b,wind,*,native_seasonal=False,prescribed_natural=False):
            return original(c,f,b,wind,native_seasonal=native_seasonal,prescribed_natural=False)
        monkeypatch.setattr(fire,'_ignition_potential',wrong);fn=fire.enrich_world_with_wildfire_disturbance
    atomic_error(w,fn)


@pytest.mark.parametrize('stage',('species','fire'))
def test_every_owned_record_field_and_new_source_descriptor_is_checked(current,stage):
    source=current['full'];key='species_range_records' if stage=='species' else 'wildfire_spread_histories'
    audit=species_audit if stage=='species' else fire_audit
    for field in source[key][0]:
        w=deepcopy(source);del w[key][0][field];assert audit(w),field
    w=deepcopy(source);w[key][0]['extra_output']=0;assert audit(w)
    if stage=='species':
        w=deepcopy(source);w[key][0]['climate_envelope']['min_temperature_c']+=1;assert audit(w)


def test_new_legacy_fire_keeps_energy_term_and_omits_activity():
    w=scalar_chain((18.,));w['cells'][0]['settlement_score']=.75;fire.enrich_world_with_wildfire_disturbance(w)
    assert w['wildfire_disturbance_model']==fire.NATURAL_PARENT_WILDFIRE_MODEL==_NATURAL_FIRE_MODELS[False]
    assert fire_audit(w)==[]
    without=scalar_chain((18.,));without['cells'][0]['climate_energy_stress_index']=0.;fire.enrich_world_with_wildfire_disturbance(without)
    assert abs(w['cells'][0]['wildfire_ignition_potential_index']-without['cells'][0]['wildfire_ignition_potential_index']-.06)<1.1e-6
    missing=scalar_chain((18.,));del missing['cells'][0]['climate_energy_stress_index'];atomic_error(missing,fire.enrich_world_with_wildfire_disturbance)


@pytest.mark.parametrize('temperatures',[(18.,18.,80.),(18.,18.,18.,80.)])
def test_one_hop_unknown_fronts_are_preserved_in_new_fire(temperatures):
    w=scalar_chain(temperatures);fire.enrich_world_with_wildfire_disturbance(w)
    assert fire_audit(w)==[]
    assert [c['wildfire_fuel_continuity_supported'] for c in w['cells']]==[True]*(len(temperatures)-2)+[False,False]
    assert w['wildfire_spread_histories']
    h=w['wildfire_spread_histories'][0];assert h['front_coverage_status']=='partial_unavailable_inputs'
    assert h['unmodelled_adjacent_cell_ids']==[len(temperatures)-2]
    assert h['containment_scope']=='coefficient_index_on_modelled_cells_not_physical_containment'
    h['unmodelled_front_edges']=[];assert fire_audit(w)


@pytest.mark.parametrize('water',('fresh_lake','saline_basin','ocean'))
def test_standing_water_is_a_barrier_but_dry_saline_is_exposed(water):
    w=scalar_chain((18.,18.,18.));w['cells'][1].update(is_lake=True,water_body_type=water)
    eco.enrich_world_with_ecosystem_dynamics(w);fire.enrich_world_with_wildfire_disturbance(w)
    assert fire_audit(w)==[];assert w['cells'][1]['wildfire_disturbance_regime']=='non_burnable_water'
    assert not w['cells'][1]['wildfire_spread_history_ids']
    dry=scalar_chain((18.,));dry['cells'][0]['water_body_type']='saline_basin';eco.enrich_world_with_ecosystem_dynamics(dry);fire.enrich_world_with_wildfire_disturbance(dry)
    assert dry['cells'][0]['wildfire_fuel_continuity_supported'] is True
    assert dry['wildfire_spread_histories']


@pytest.mark.parametrize('temperature',[None,True,'18',math.nan,math.inf,1<<20000],ids=['null','bool','text','nan','inf','hugeint'])
def test_fire_retains_parent_unavailable_T_but_species_own_annual_preflight_rejects(temperature):
    w=scalar_chain((temperature,));fire.enrich_world_with_wildfire_disturbance(w)
    assert fire_audit(w)==[] and w['cells'][0]['wildfire_disturbance_regime']=='fuel_proxy_unavailable'
    atomic_error(w,species.enrich_world_with_species_ranges)


def test_empty_new_stages_publish_valid_zero_envelopes():
    w={'cells':[],'summary':{},'wetland_systems':[],'reef_systems':[],'aquifer_systems':[]};eco.enrich_world_with_ecosystem_dynamics(w)
    species.enrich_world_with_species_ranges(w);fire.enrich_world_with_wildfire_disturbance(w)
    assert species_audit(w)==fire_audit(w)==[]
    assert w['species_range_records']==w['wildfire_spread_histories']==[]


@pytest.mark.parametrize("scope", ("full", "geo"))
def test_fresh_publication_clears_and_rebuilds_all_ten_score_flags(scope):
    guilds = {"canopy_tree", "grassland_grazer", "desert_specialist", "alpine_tundra_specialist", "large_predator", "wetland_amphibian", "freshwater_fish", "marine_fish", "reef_builder", "mangrove_coastal_bird"}
    flags = {f"species_{guild}_score_supported" for guild in guilds}
    assert flags.issubset(SPECIES_CELLS)
    w = build_to_species_inputs(fresh_activity_world(scope))
    assert not any(flags.intersection(c) for c in w["cells"])
    before_cells = [set(c) for c in w["cells"]]
    before_summary = set(w["summary"])
    species.enrich_world_with_species_ranges(w)
    assert all(set(c) - before == set(SPECIES_CELLS) for c, before in zip(w["cells"], before_cells))
    assert set(w["summary"]) - before_summary == set(SPECIES_SUMMARY)
    assert all(all(type(c[flag]) is bool for flag in flags) for c in w["cells"])
    assert species_audit(w) == []
    for flag in ("species_freshwater_fish_score_supported", "species_marine_fish_score_supported"):
        stale = build_to_species_inputs(fresh_activity_world(scope))
        stale["cells"][0][flag] = False
        atomic_error(stale, species.enrich_world_with_species_ranges)


@pytest.mark.parametrize("stage", ("species", "fire"))
@pytest.mark.parametrize("bad", [None, True, "0", [], {}, math.nan, math.inf, 1 << 20000], ids=["null", "bool", "text", "list", "dict", "nan", "inf", "hugeint"])
def test_explicit_child_descriptor_types_are_atomic_and_diagnostic(current, stage, bad):
    w = deepcopy(current["full"])
    field = "river_channel_width_m" if stage == "species" else "floodplain_connectivity_index"
    w["cells"][-1][field] = bad
    fn, audit = (species.enrich_world_with_species_ranges, species_audit) if stage == "species" else (fire.enrich_world_with_wildfire_disturbance, fire_audit)
    atomic_error(w, fn)
    assert field in audit(w)[0]


@pytest.mark.parametrize("stage", ("species", "fire"))
def test_current_parent_cannot_hide_deleted_own_declaration_and_all_outputs(current, stage):
    w = deepcopy(current["full"])
    if stage == "species":
        clear_stage(w, SPECIES_CELLS, SPECIES_SUMMARY, ("species_ranges_model", "species_range_records"))
        errors = species_audit(w)
    else:
        clear_stage(w, FIRE_CELLS, FIRE_SUMMARY, ("wildfire_disturbance_model", "wildfire_spread_histories"))
        errors = fire_audit(w)
    assert errors and "declaration" in errors[0]


def test_native_and_legacy_natural_fire_names_are_not_interchangeable(current):
    native = deepcopy(current["full"])
    native["wildfire_disturbance_model"] = deepcopy(fire.NATURAL_PARENT_WILDFIRE_MODEL)
    atomic_error(native, fire.enrich_world_with_wildfire_disturbance)
    assert fire_audit(native)
    legacy = scalar_chain((18.,))
    legacy["wildfire_disturbance_model"] = deepcopy(fire.NATIVE_NATURAL_PARENT_WILDFIRE_MODEL)
    atomic_error(legacy, fire.enrich_world_with_wildfire_disturbance)
    assert fire_audit(legacy)


@pytest.mark.parametrize("family,descriptor", [("wetland_systems", "wetland_system_id"), ("reef_systems", "reef_system_id"), ("aquifer_systems", "aquifer_system_id")])
@pytest.mark.parametrize("kind", ["missing", "null", "mapping", "empty", "record-null", "duplicate-id", "negative-id", "bool-id", "list-id", "members-missing", "member-unknown", "member-duplicate", "member-bool", "descriptor-unknown", "descriptor-cleared", "member-removed"])
def test_species_source_families_are_explicit_and_reciprocal(current, family, descriptor, kind):
    w = deepcopy(current["full"])
    rec = w[family][0]
    cid = rec["cell_ids"][0]
    if kind == "missing": del w[family]
    elif kind == "null": w[family] = None
    elif kind == "mapping": w[family] = {}
    elif kind == "empty": w[family] = []
    elif kind == "record-null": w[family][0] = None
    elif kind == "duplicate-id": w[family].append(deepcopy(rec))
    elif kind == "negative-id": rec["id"] = -1
    elif kind == "bool-id": rec["id"] = True
    elif kind == "list-id": rec["id"] = []
    elif kind == "members-missing": del rec["cell_ids"]
    elif kind == "member-unknown": rec["cell_ids"].append(99999)
    elif kind == "member-duplicate": rec["cell_ids"].append(cid)
    elif kind == "member-bool": rec["cell_ids"][0] = True
    elif kind == "descriptor-unknown": w["cells"][cid][descriptor] = 99999
    elif kind == "descriptor-cleared": w["cells"][cid][descriptor] = -1
    else: rec["cell_ids"].remove(cid)
    atomic_error(w, species.enrich_world_with_species_ranges)
    assert species_audit(w)


def test_species_basin_namespace_is_native_outlet_cells_and_not_source_record_ids(current):
    w = deepcopy(current["full"])
    w["cells"][0]["basin_id"] = 99999
    atomic_error(w, species.enrich_world_with_species_ranges)
    assert "outlet cell" in species_audit(w)[0]
    scalar = scalar_chain((18.,))
    scalar["cells"][0]["basin_id"] = 0
    species.enrich_world_with_species_ranges(scalar)
    assert species_audit(scalar) == []


@pytest.mark.parametrize("stage", ("species", "fire"))
def test_every_new_model_field_has_exact_declared_type_and_value(current, stage):
    key = "species_ranges_model" if stage == "species" else "wildfire_disturbance_model"
    fn, audit = (species.enrich_world_with_species_ranges, species_audit) if stage == "species" else (fire.enrich_world_with_wildfire_disturbance, fire_audit)
    for field in current["full"][key]:
        w = deepcopy(current["full"])
        w[key][field] = None
        atomic_error(w, fn)
        assert audit(w), field


@pytest.mark.parametrize("bad", [None, [], True, 1, "world"])
def test_new_entrypoint_and_independent_root_errors_are_deliberate(bad):
    for fn, audit in ((species.enrich_world_with_species_ranges, species_audit), (fire.enrich_world_with_wildfire_disturbance, fire_audit)):
        with pytest.raises(ValueError): fn(bad)
        assert audit(bad)


def test_supported_zero_fuel_is_not_unknown_or_a_thermal_barrier():
    w = scalar_chain((18.,))
    c = w["cells"][0]
    c.update(temperature_c=math.nextafter(52., 0.), precipitation_mm_y=0., soil_moisture_index=0., fertility=0., growing_season_months=0., soil_organic_matter_fraction=0., biome="hot_desert", fire_frequency_index=0., ecotone_index=0., seasonal_aridity_index=0., wind_east=0., wind_north=0.)
    eco.enrich_world_with_ecosystem_dynamics(w)
    fire.enrich_world_with_wildfire_disturbance(w)
    assert c["vegetation_biomass_index"] == 0.0
    assert c["wildfire_fuel_continuity_supported"] is True
    assert c["wildfire_fuel_continuity_index"] == 0.0
    assert c["wildfire_disturbance_regime"] != "fuel_proxy_unavailable"
    assert fire_audit(w) == []



def test_finite_parent_values_cannot_publish_an_overflowed_species_record_mean():
    w = scalar_chain((18.,18.,18.))
    for c in w["cells"]: c["precipitation_mm_y"] = 1e308
    eco.enrich_world_with_ecosystem_dynamics(w)
    assert validate_aquatic_climate_support(w) == []
    atomic_error(w, species.enrich_world_with_species_ranges)


@pytest.mark.parametrize("field", ("mean_precipitation_mm_y", "climate_envelope"))
def test_nonfinite_species_descriptor_output_is_not_exact_replay(current, field):
    w = deepcopy(current["full"])
    r = w["species_range_records"][0]
    if field == "climate_envelope": r[field]["mean_precipitation_mm_y"] = math.inf
    else: r[field] = math.inf
    assert any("finite record outputs" in e for e in species_audit(w))



def test_retained_native_fire3_archive_keeps_exact_historical_output():
    w = json.loads(gzip.decompress((Path(__file__).parent / "fixtures/wildfire_parent_availability/native_v3_world.json.gz").read_bytes()))
    assert w["wildfire_disturbance_model"]["model"] == "heuristic_wildfire_native_seasonal_v3"
    assert fire_audit(w) == []
    before = json.dumps(w, sort_keys=True)
    fire.enrich_world_with_wildfire_disturbance(w)
    assert json.dumps(w, sort_keys=True) == before
    assert fire_audit(w) == []
